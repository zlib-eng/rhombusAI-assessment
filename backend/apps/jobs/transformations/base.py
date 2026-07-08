from abc import ABC, abstractmethod


class Transformation(ABC):
    """
    Every transformation type implements exactly these two methods.
    tasks.py only ever talks to THIS interface — it never knows or
    cares whether it's doing find/replace, extraction, or formatting.
    Adding a new transformation type never requires editing tasks.py.
    """

    @abstractmethod
    def generate_spec(self, prompt: str) -> dict:
        """Calls the LLM (if needed), returns a JSON-serializable dict."""
        raise NotImplementedError

    @abstractmethod
    def apply(self, df, target_column: str, spec: dict, job):
        """Applies the transformation to the Spark DataFrame."""
        raise NotImplementedError