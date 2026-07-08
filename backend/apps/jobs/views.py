import os
import uuid

import pandas as pd
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from celery.result import AsyncResult
import celery

from .models import Job
from .serializers import JobCreateSerializer, JobSerializer
from .tasks import process_file_task

MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500MB


class JobCreateView(APIView):
    """
    POST /api/jobs/
    Accepts a file upload + job parameters, saves the file, creates a
    Job record, dispatches the Celery task, returns the job ID
    immediately — never blocks on processing.
    """

    def post(self, request):
        serializer = JobCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        file = serializer.validated_data['file']
        nl_prompt = serializer.validated_data['nl_prompt']
        target_column = serializer.validated_data['target_column']
        transformation_type = serializer.validated_data['transformation_type']
        replacement_value = serializer.validated_data.get('replacement_value', '')
        output_column_name = serializer.validated_data.get('output_column_name', '')

        # Conditional requirements per transformation type.
        if (transformation_type == Job.TransformationType.FIND_REPLACE
                and not replacement_value):
            return Response(
                {'error': 'replacement_value is required for Find and Replace'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if (transformation_type == Job.TransformationType.EXTRACT
                and not output_column_name):
            return Response(
                {'error': 'output_column_name is required for Extract to New Column'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # File type validation.
        allowed_extensions = ['.csv', '.xlsx']
        file_extension = os.path.splitext(file.name)[1].lower()
        if file_extension not in allowed_extensions:
            return Response(
                {'error': f'Unsupported file type: {file_extension}. '
                          'Please upload a CSV or Excel file.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # File size validation.
        if file.size > MAX_FILE_SIZE_BYTES:
            return Response(
                {'error': f'File too large ({file.size / 1024 / 1024:.1f}MB). '
                          f'Maximum allowed is {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f}MB.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Save the file to the shared volume.
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        input_dir = os.path.join(settings.SHARED_FILES_PATH, 'input')
        os.makedirs(input_dir, exist_ok=True)
        file_path = os.path.join(input_dir, unique_filename)

        with open(file_path, 'wb') as destination:
            for chunk in file.chunks():
                destination.write(chunk)

        # Create the Job record.
        job = Job.objects.create(
            status=Job.Status.QUEUED,
            input_file_path=file_path,
            nl_prompt=nl_prompt,
            target_column=target_column,
            transformation_type=transformation_type,
            replacement_value=replacement_value,
            output_column_name=output_column_name or None,
        )

        # Dispatch the Celery task and store its ID.
        task = process_file_task.delay(str(job.id))
        job.celery_task_id = task.id
        job.save(update_fields=['celery_task_id'])

        return Response(
            JobSerializer(job).data,
            status=status.HTTP_201_CREATED
        )


class FileColumnsView(APIView):
    """
    POST /api/jobs/columns/
    Reads only the header row of an uploaded file and returns the
    usable column names, so React can populate the column dropdown.
    """

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        file_extension = os.path.splitext(file.name)[1].lower()
        if file_extension not in ['.csv', '.xlsx']:
            return Response(
                {'error': 'Unsupported file type'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if file_extension == '.csv':
                df = pd.read_csv(file, nrows=0)
            else:
                df = pd.read_excel(file, nrows=0)

            all_columns = df.columns.tolist()

            if not all_columns:
                return Response(
                    {'error': 'File appears to have no columns'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Pandas auto-names blank header cells "Unnamed: N"; Spark
            # names the same cells differently (_c0, _c1...), so a
            # column selected under its pandas name would fail in the
            # Spark stage. Exclude unnamed columns from selection; only
            # reject the file outright if NO usable columns remain.
            named_columns = [
                c for c in all_columns if not str(c).startswith('Unnamed:')
            ]
            excluded_count = len(all_columns) - len(named_columns)

            if not named_columns:
                return Response(
                    {'error': (
                        'This file has no valid column headers — the '
                        'first row appears to be blank or malformed. '
                        'Please check that the first row contains proper '
                        'column names, then re-upload.'
                    )},
                    status=status.HTTP_400_BAD_REQUEST
                )

            response_data = {'columns': named_columns}
            if excluded_count > 0:
                response_data['warning'] = (
                    f'{excluded_count} column(s) with blank headers were '
                    'excluded from selection.'
                )

            return Response(response_data)

        except Exception as e:
            return Response(
                {'error': f'Could not read file: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )


class JobStatusView(APIView):
    """
    GET /api/jobs/{id}/status/
    Returns current status and progress. React polls this every 2s.
    """

    def get(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        progress = job.progress
        if job.celery_task_id:
            task_result = AsyncResult(job.celery_task_id)
            if task_result.state == 'PROGRESS':
                progress = task_result.info.get('progress', job.progress)

        return Response({
            'id': str(job.id),
            'status': job.status,
            'progress': progress,
            'error_message': job.error_message,
        })


class JobCancelView(APIView):
    """
    POST /api/jobs/{id}/cancel/
    Marks the job CANCELLED and revokes the Celery task.
    """

    def post(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if job.status not in [Job.Status.QUEUED, Job.Status.RUNNING]:
            return Response(
                {'error': f'Cannot cancel a job with status {job.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        job.status = Job.Status.CANCELLED
        job.save(update_fields=['status', 'updated_at'])

        if job.celery_task_id:
            celery.current_app.control.revoke(
                job.celery_task_id,
                terminate=True,
                signal='SIGTERM'
            )

        return Response({'status': 'CANCELLED'})


class JobResultsView(APIView):
    """
    GET /api/jobs/{id}/results/?page=0
    Returns one page of processed results from the Parquet output.
    """
    PAGE_SIZE = 100

    def get(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if job.status != Job.Status.SUCCESS:
            return Response(
                {'error': f'Results not available. Job status: {job.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not job.output_path:
            return Response(
                {'error': 'No output file found for this job'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            page = int(request.query_params.get('page', 0))

            df = pd.read_parquet(job.output_path)

            total_rows = len(df)
            total_pages = max(1, (total_rows + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

            if page < 0 or page >= total_pages:
                return Response(
                    {'error': f'Page {page} out of range. '
                              f'Valid range: 0 to {total_pages - 1}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            start = page * self.PAGE_SIZE
            end = start + self.PAGE_SIZE
            page_df = df.iloc[start:end]

            # Convert to plain dicts FIRST, then clean NaN per-value.
            # Cleaning while still a DataFrame silently fails for
            # numeric columns (pandas coerces None back to NaN in
            # float64 columns); as plain Python scalars, None sticks.
            raw_rows = page_df.to_dict(orient='records')
            rows = [
                {k: (None if pd.isna(v) else v) for k, v in record.items()}
                for record in raw_rows
            ]

            return Response({
                'rows': rows,
                'columns': list(df.columns),
                'total_rows': total_rows,
                'total_pages': total_pages,
                'page': page,
                'page_size': self.PAGE_SIZE,
            })

        except Exception as e:
            return Response(
                {'error': f'Could not read results: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )