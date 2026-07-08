import os
from celery import shared_task
from celery.utils.log import get_task_logger
from django.conf import settings

from .models import Job
from .llm_utils import get_regex_pattern, RegexGenerationError

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def process_file_task(self, job_id):
    try:
        job = Job.objects.get(id=job_id)
    except Job.DoesNotExist:
        logger.error(f"Job {job_id} not found in database")
        return

    logger.info(f"Starting job {job_id}")
    spark = None

    try:
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
            ColumnNotFoundError,
        )

        spark = get_spark_session()
        df = read_file(spark, job.input_file_path)
        row_count = df.count()
        logger.info(f"Job {job_id}: Read {row_count} rows")

        # ── Stage 2: Generate regex from the prompt ─────────────
        _update_progress(self, job, 30)
        logger.info(f"Job {job_id}: Generating regex from prompt (30%)")

        job.refresh_from_db()
        if job.status == Job.Status.CANCELLED:
            logger.info(f"Job {job_id} cancelled before regex generation")
            return

        try:
            pattern = get_regex_pattern(job.nl_prompt)
        except RegexGenerationError as e:
            # Permanent failure — the prompt produced an unusable
            # pattern. Retrying won't help, so fail immediately
            # instead of going through the retry/backoff cycle.
            logger.error(f"Job {job_id}: regex generation failed — {e}")
            job.status = Job.Status.FAILED
            job.error_message = str(e)
            job.save(update_fields=['status', 'error_message', 'updated_at'])
            return

        logger.info(f"Job {job_id}: Using pattern '{pattern}'")

        # ── Stage 3: Apply transformation ───────────────────────
        _update_progress(self, job, 60)
        logger.info(f"Job {job_id}: Applying transformation (60%)")

        job.refresh_from_db()
        if job.status == Job.Status.CANCELLED:
            logger.info(f"Job {job_id} cancelled before transformation")
            return

        try:
            df_transformed = apply_regex_transformation(
                df,
                job.target_column,
                pattern,
                job.replacement_value,
            )
        except ColumnNotFoundError as e:
            # Also a permanent failure — the column will never exist
            # no matter how many times we retry the same job. Fail
            # immediately rather than burning through backoff delays
            # (5s, 25s, 125s) on a guaranteed repeat failure.
            logger.error(f"Job {job_id}: column error — {e}")
            job.status = Job.Status.FAILED
            job.error_message = str(e)
            job.save(update_fields=['status', 'error_message', 'updated_at'])
            return

        # ── Stage 4: Write output ────────────────────────────────
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

        # ── Stage 5: Complete ────────────────────────────────────
        job.status = Job.Status.SUCCESS
        job.progress = 100
        job.output_path = output_path
        job.save(update_fields=['status', 'progress', 'output_path', 'updated_at'])
        _update_progress(self, job, 100)

        logger.info(f"Job {job_id} completed — {row_count} rows processed")

    except Exception as exc:
        # Anything NOT caught above — network errors calling the LLM,
        # unexpected Spark failures, etc. These are worth retrying.
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
        if spark:
            try:
                spark.stop()
            except Exception:
                pass


def _update_progress(task, job, progress_value):
    task.update_state(
        state='PROGRESS',
        meta={
            'progress': progress_value,
            'job_id': str(job.id),
        }
    )
    job.progress = progress_value
    job.save(update_fields=['progress', 'updated_at'])