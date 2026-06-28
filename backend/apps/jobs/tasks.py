import os
from celery import shared_task
from celery.utils.log import get_task_logger
from django.conf import settings

from .models import Job

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def process_file_task(self, job_id):
    """
    Processes an uploaded file using PySpark.
    Reads the file, applies a regex transformation,
    and writes the result to Parquet.
    """

    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        logger.error(f"Job {job_id} not found in database")
        return

    logger.info(f"Starting job {job_id}")
    spark = None

    try:
        # Mark as RUNNING
        job.status = Job.Status.RUNNING
        job.progress = 0
        job.save(update_fields=['status', 'progress', 'updated_at'])
        _update_progress(self, job, 0)

        # ── Stage 1: Read the file ──────────────────────────────
        _update_progress(self, job, 10)
        logger.info(f"Job {job_id}: Reading file (10%)")

        job.refresh_from_db()
        if job.status == Job.Status.CANCELLED:
            logger.info(f"Job {job_id} cancelled before reading")
            return

        from .spark_utils import (
            get_spark_session,
            read_file,
            apply_regex_transformation,
            write_output,
        )

        spark = get_spark_session()
        df = read_file(spark, job.input_file_path)
        row_count = df.count()
        logger.info(f"Job {job_id}: Read {row_count} rows")

        # ── Stage 2: Apply transformation ───────────────────────
        _update_progress(self, job, 50)
        logger.info(f"Job {job_id}: Applying transformation (50%)")

        job.refresh_from_db()
        if job.status == Job.Status.CANCELLED:
            logger.info(f"Job {job_id} cancelled before transformation")
            return

        # HARDCODED regex for Step 4.
        # Replaced with LLM-generated pattern in Step 5.
        hardcoded_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b'

        df_transformed = apply_regex_transformation(
            df,
            job.target_column,
            hardcoded_pattern,
            job.replacement_value,
        )

        # ── Stage 3: Write output ────────────────────────────────
        _update_progress(self, job, 85)
        logger.info(f"Job {job_id}: Writing output (85%)")

        job.refresh_from_db()
        if job.status == Job.Status.CANCELLED:
            logger.info(f"Job {job_id} cancelled before writing")
            return

        output_path = os.path.join(
            settings.SHARED_FILES_PATH,
            'output',
            str(job.id)
        )
        write_output(df_transformed, output_path)

        # ── Stage 4: Complete ────────────────────────────────────
        job.status = Job.Status.SUCCESS
        job.progress = 100
        job.output_path = output_path
        job.save(update_fields=['status', 'progress', 'output_path', 'updated_at'])
        _update_progress(self, job, 100)

        logger.info(f"Job {job_id} completed — {row_count} rows processed")

    except Exception as exc:
        logger.error(f"Job {job_id} failed: {exc}")

        try:
            raise self.retry(
                exc=exc,
                countdown=5 ** (self.request.retries + 1)
            )
        except self.MaxRetriesExceededError:
            job.status = Job.Status.FAILED
            job.error_message = str(exc)
            job.save(update_fields=['status', 'error_message', 'updated_at'])

    finally:
        # Always stop the SparkSession when the task ends.
        # Leaving it running would hold JVM resources indefinitely.
        if spark:
            try:
                spark.stop()
            except Exception:
                pass


def _update_progress(task, job, progress_value):
    """Updates progress in Redis (live) and PostgreSQL (durable)."""
    task.update_state(
        state='PROGRESS',
        meta={
            'progress': progress_value,
            'job_id': str(job.id),
        }
    )
    job.progress = progress_value
    job.save(update_fields=['progress', 'updated_at'])