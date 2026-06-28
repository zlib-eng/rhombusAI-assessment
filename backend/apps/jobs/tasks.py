import time
from celery import shared_task
from celery.utils.log import get_task_logger

from .models import Job

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def process_file_task(self, job_id):
    """
    The main processing task. In this step it fakes work by sleeping.
    In Step 4 this will be replaced with real PySpark processing.

    bind=True gives us access to `self` — the task instance.
    This lets us call self.update_state() and self.retry().

    max_retries=3 — if the task raises an exception, Celery
    will retry it up to 3 times before marking it FAILED.

    default_retry_delay=5 — wait 5 seconds before the first retry.
    Combined with exponential backoff below, retries wait
    5s, 25s, 125s before giving up.
    """

    # Step 1: Load the Job from the database.
    # If the job doesn't exist, fail immediately — no point retrying.
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        logger.error(f"Job {job_id} not found in database")
        return

    logger.info(f"Starting job {job_id}")

    try:
        # Step 2: Mark the job as RUNNING in PostgreSQL
        # and report 0% progress to Redis.
        job.status = Job.Status.RUNNING
        job.progress = 0
        job.save(update_fields=['status', 'progress', 'updated_at'])

        _update_progress(self, job, 0)

        # ----------------------------------------------------------------
        # FAKE WORK — this entire block gets replaced in Step 4
        # with real PySpark processing.
        # For now we just sleep and update progress in stages.
        # ----------------------------------------------------------------
        stages = [
            (10,  "Reading file"),
            (30,  "Generating regex from prompt"),
            (60,  "Applying transformation"),
            (85,  "Writing output"),
            (100, "Complete"),
        ]

        for progress_value, stage_name in stages:
            # Check if the job was cancelled before doing the next stage.
            # Re-read from the database to get the latest status.
            job.refresh_from_db()
            if job.status == Job.Status.CANCELLED:
                logger.info(f"Job {job_id} was cancelled, stopping")
                return

            logger.info(f"Job {job_id}: {stage_name} ({progress_value}%)")

            # Simulate work taking time
            time.sleep(3)

            # Update progress in both Redis and PostgreSQL
            _update_progress(self, job, progress_value)
        # ----------------------------------------------------------------

        # Step 3: Mark the job as SUCCESS.
        job.status = Job.Status.SUCCESS
        job.progress = 100
        job.save(update_fields=['status', 'progress', 'updated_at'])

        logger.info(f"Job {job_id} completed successfully")

    except Exception as exc:
        # Something unexpected went wrong.
        # Try to retry with exponential backoff.
        # If we've hit max_retries, mark the job as FAILED.
        logger.error(f"Job {job_id} failed: {exc}")

        try:
            # exponential=True means wait 5s, then 25s, then 125s
            raise self.retry(exc=exc, countdown=5 ** (self.request.retries + 1))

        except self.MaxRetriesExceededError:
            # We've used all our retries — give up and mark as FAILED
            job.status = Job.Status.FAILED
            job.error_message = str(exc)
            job.save(update_fields=['status', 'error_message', 'updated_at'])


def _update_progress(task, job, progress_value):
    """
    Helper that updates progress in two places simultaneously:

    1. Redis — via Celery's update_state(). This is what the
       polling endpoint reads in real time.

    2. PostgreSQL — via the Job model. This is the durable record.
       If Redis restarts, the last known progress is still in the DB.
    """
    task.update_state(
        state='PROGRESS',
        meta={
            'progress': progress_value,
            'job_id': str(job.id),
        }
    )

    job.progress = progress_value
    job.save(update_fields=['progress', 'updated_at'])