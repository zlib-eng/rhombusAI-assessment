from pyspark.sql.functions import upper, lower, initcap, trim, col
from .base import Transformation
from ..llm_utils import get_format_operation

# Maps the LLM's constrained choice directly to native Spark functions.
SPARK_FORMAT_FUNCTIONS = {
    "UPPER": upper,
    "LOWER": lower,
    "INITCAP": initcap,
    "TRIM": trim,
}


class StandardizeFormatTransformation(Transformation):
    def generate_spec(self, prompt):
        # Deliberately different pattern from the other two: instead of
        # free-form regex generation + syntax validation, the LLM picks
        # from a small fixed allow-list. Demonstrates that LLM output
        # can be constrained to a safe enum rather than always needing
        # open-ended validation.
        operation = get_format_operation(prompt)
        return {"operation": operation}

    def apply(self, df, target_column, spec, job):
        spark_fn = SPARK_FORMAT_FUNCTIONS[spec["operation"]]
        return df.withColumn(target_column, spark_fn(col(target_column)))