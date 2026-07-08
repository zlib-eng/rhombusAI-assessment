from pyspark.sql.functions import regexp_extract, col
from .base import Transformation
from ..llm_utils import get_regex_pattern


class ExtractTransformation(Transformation):
    def generate_spec(self, prompt):
        # Reuses the same regex-generation path as FIND_REPLACE — the
        # LLM's job (turn English into a pattern) is identical; only
        # what happens with the match afterward differs.
        pattern = get_regex_pattern(prompt)
        return {"pattern": pattern}

    def apply(self, df, target_column, spec, job):
        output_col = job.output_column_name or f"{target_column}_extracted"
        return df.withColumn(
            output_col,
            regexp_extract(col(target_column), spec["pattern"], 0)
        )