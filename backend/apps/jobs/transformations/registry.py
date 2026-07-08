from .find_replace import FindReplaceTransformation
from .extract import ExtractTransformation
from .standardize_format import StandardizeFormatTransformation

TRANSFORMATION_REGISTRY = {
    "FIND_REPLACE": FindReplaceTransformation,
    "EXTRACT": ExtractTransformation,
    "STANDARDIZE_FORMAT": StandardizeFormatTransformation,
}


def get_transformation(transformation_type: str):
    """
    Adding a future transformation type means: write a new class
    implementing Transformation, add ONE line here. tasks.py is
    never touched — this is Open/Closed in practice.
    """
    cls = TRANSFORMATION_REGISTRY.get(transformation_type)
    if cls is None:
        raise ValueError(f"Unknown transformation type: {transformation_type}")
    return cls()