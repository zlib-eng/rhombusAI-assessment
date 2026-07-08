from pyspark.sql.functions import regexp_replace, col
from .base import Transformation
from ..llm_utils import get_regex_pattern


class FindReplaceTransformation(Transformation):
    def generate_spec(self, prompt):
        pattern = get_regex_pattern(prompt)
        return {"pattern": pattern}

    def apply(self, df, target_column, spec, job):
        return df.withColumn(
            target_column,
            regexp_replace(col(target_column), spec["pattern"], job.replacement_value)
        )