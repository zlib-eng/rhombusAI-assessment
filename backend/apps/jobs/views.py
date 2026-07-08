import os
import uuid
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Job
from .serializers import JobCreateSerializer, JobSerializer
from .tasks import process_file_task
from celery.result import AsyncResult
import pandas as pd

from celery.app.control import Control
import celery

class JobResultsView(APIView):
    """
    GET /api/jobs/{id}/results/?page=0
    Returns one page of processed results from the Parquet output.
    Page numbering is zero-based.
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

            # pandas.read_parquet handles a directory of part files
            # automatically — we don't need to worry about how many
            # files Spark created.
            df = pd.read_parquet(job.output_path)

            total_rows = len(df)
            total_pages = max(1, (total_rows + self.PAGE_SIZE - 1) // self.PAGE_SIZE)

            if page < 0 or page >= total_pages:
                return Response(
                    {'error': f'Page {page} out of range. Valid range: 0 to {total_pages - 1}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            start = page * self.PAGE_SIZE
            end = start + self.PAGE_SIZE
            page_df = df.iloc[start:end]

            # Convert to plain dicts FIRST, then clean NaN per-value. Doing the
            # NaN replacement while data is still a DataFrame (the previous
            # approach) silently fails for numeric columns — pandas coerces None
            # back into NaN when assigned into a float64 column, since every
            # value in a numpy column must share one dtype. Once converted to a
            # list of dicts, each value is a plain Python scalar with no such
            # constraint, so None can be swapped in reliably for any dtype.
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

class JobCancelView(APIView):
    """
    POST /api/jobs/{id}/cancel/
    Signals the running Celery worker to stop and marks the job CANCELLED.
    """

    def post(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Can only cancel a job that is queued or running
        if job.status not in [Job.Status.QUEUED, Job.Status.RUNNING]:
            return Response(
                {'error': f'Cannot cancel a job with status {job.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Mark as CANCELLED in PostgreSQL first.
        # The task itself checks for this status and exits cleanly.
        job.status = Job.Status.CANCELLED
        job.save(update_fields=['status', 'updated_at'])

        # Tell Celery to revoke the task.
        # terminate=True sends SIGTERM to the worker process if it's running.
        if job.celery_task_id:
            celery.current_app.control.revoke(
                job.celery_task_id,
                terminate=True,
                signal='SIGTERM'
            )

        return Response({'status': 'CANCELLED'})

class JobStatusView(APIView):
    """
    GET /api/jobs/{id}/status/
    Returns the current status and progress of a job.
    React calls this every 2 seconds while a job is running.
    """

    def get(self, request, job_id):
        # Load the Job from PostgreSQL
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return Response(
                {'error': 'Job not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # If we have a Celery task ID, read the live state from Redis.
        # This gives us real-time progress even between database saves.
        progress = job.progress
        if job.celery_task_id:
            task_result = AsyncResult(job.celery_task_id)
            if task_result.state == 'PROGRESS':
                # Live progress from Redis — more up to date than the DB
                progress = task_result.info.get('progress', job.progress)

        return Response({
            'id': str(job.id),
            'status': job.status,
            'progress': progress,
            'error_message': job.error_message,
        })


class FileColumnsView(APIView):
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

            # Pandas auto-names blank header cells "Unnamed: N". Spark's
            # CSV reader names the same blank cells completely differently
            # (_c0, _c1...), so selecting a column under its pandas name
            # would silently fail once the file reaches PySpark.
            #
            # Rather than reject the whole file — too aggressive when
            # only a few trailing columns are blank, a common artifact
            # of spreadsheet exports with stray trailing commas — we
            # exclude just the unnamed columns from the selectable list.
            # The file is still usable via its properly-named columns.
            named_columns = [c for c in all_columns if not str(c).startswith('Unnamed:')]
            excluded_count = len(all_columns) - len(named_columns)

            if not named_columns:
                # Every column is unnamed — no usable header at all
                # (e.g. a blank row sitting above the real header row).
                # Nothing salvageable; reject outright.
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

class JobCreateView(APIView):
    """
    POST /api/jobs/
    Accepts a file upload + job parameters.
    Saves the file, creates a Job record, returns the job ID.
    Does NOT start any processing — that comes in Step 3.
    """

    def post(self, request):
        # Step 1: Validate the incoming data using our serializer.
        # If anything is missing or wrong, this returns a 400 error automatically.
        serializer = JobCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 2: Pull out the validated values.
        file = serializer.validated_data['file']
        nl_prompt = serializer.validated_data['nl_prompt']
        target_column = serializer.validated_data['target_column']
        replacement_value = serializer.validated_data['replacement_value']

        # Step 3: Validate the file type.
        # We only accept CSV and Excel files.
        allowed_extensions = ['.csv', '.xlsx']
        file_extension = os.path.splitext(file.name)[1].lower()
        if file_extension not in allowed_extensions:
            return Response(
                {'error': f'Unsupported file type: {file_extension}. Please upload a CSV or Excel file.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500MB — adjust to whatever you've tested

        if file.size > MAX_FILE_SIZE_BYTES:
            return Response(
                {'error': f'File too large ({file.size / 1024 / 1024:.1f}MB). Maximum allowed is {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f}MB.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 4: Save the file to the shared volume.
        # We generate a unique filename using UUID to avoid collisions.
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        input_dir = os.path.join(settings.SHARED_FILES_PATH, 'input')
        os.makedirs(input_dir, exist_ok=True)
        file_path = os.path.join(input_dir, unique_filename)

        with open(file_path, 'wb') as destination:
            for chunk in file.chunks():
                destination.write(chunk)

        # Step 5: Create the Job record in PostgreSQL.
        job = Job.objects.create(
            status=Job.Status.QUEUED,
            input_file_path=file_path,
            nl_prompt=nl_prompt,
            target_column=target_column,
            replacement_value=replacement_value,
        )

        # Step 6: Dispatch the Celery task.
        # .delay() serialises the job_id and pushes it onto the Redis queue.
        # This returns immediately — it does NOT wait for the task to finish.
        task = process_file_task.delay(str(job.id))

        # Step 7: Store Celery's task ID on the Job record.
        # We need this later to look up the task's live state in Redis.
        job.celery_task_id = task.id
        job.save(update_fields=['celery_task_id'])

        # Step 8: Return the job to React immediately.
        return Response(
            JobSerializer(job).data,
            status=status.HTTP_201_CREATED
        )