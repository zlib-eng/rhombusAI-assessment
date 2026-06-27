import uuid
from django.db import models


class Job(models.Model):
    """
    The model is a Python class that Django translates into a PostgreSQL table. 
    Each attribute on the class becomes a column in the table.
    """

    class Status(models.TextChoices):
        QUEUED = 'QUEUED', 'Queued'
        RUNNING = 'RUNNING', 'Running'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    # Primary key — a UUID instead of a sequential integer.
    # UUIDs are safer to expose in URLs because they're not guessable.
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    # Current state of the job.
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED
    )

    # How far through processing we are, 0-100.
    progress = models.IntegerField(default=0)

    # Where the uploaded file lives on the shared volume.
    input_file_path = models.CharField(max_length=500)

    # Where PySpark writes the processed output.
    # Null until the job succeeds.
    output_path = models.CharField(
        max_length=500,
        null=True,
        blank=True
    )

    # The natural language description the user typed.
    nl_prompt = models.TextField()

    # Which column to apply the transformation to.
    target_column = models.CharField(max_length=255)

    # What to replace matched text with.
    replacement_value = models.CharField(max_length=500)

    # Celery's internal task ID — the bridge between our Job
    # record and Celery's Redis state.
    # Null until Django dispatches the task.
    celery_task_id = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    # Human-readable error description if the job fails.
    error_message = models.TextField(
        null=True,
        blank=True
    )

    # Automatic timestamps.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Job {self.id} [{self.status}]"

    class Meta:
        ordering = ['-created_at']