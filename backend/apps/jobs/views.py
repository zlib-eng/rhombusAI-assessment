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
    """
    POST /api/jobs/columns/
    Accepts a file, reads only the header row,
    returns the column names as a list.
    Used by React to populate the column dropdown
    before the user submits the full job.
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
                # Read only the first row — nrows=0 gives headers only
                df = pd.read_csv(file, nrows=0)
            else:
                df = pd.read_excel(file, nrows=0)

            columns = df.columns.tolist()

            if not columns:
                return Response(
                    {'error': 'File appears to have no columns'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return Response({'columns': columns})

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