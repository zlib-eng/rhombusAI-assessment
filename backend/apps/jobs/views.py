import os
import uuid
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Job
from .serializers import JobCreateSerializer, JobSerializer


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

        # Step 6: Return the job ID to React immediately.
        # We are NOT starting any processing here.
        # The response comes back in milliseconds.
        return Response(
            JobSerializer(job).data,
            status=status.HTTP_201_CREATED
        )