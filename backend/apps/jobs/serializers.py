from rest_framework import serializers
from .models import Job


class JobCreateSerializer(serializers.Serializer):
    """
    Validates the data coming IN from React when creating a job.
    replacement_value and output_column_name are conditionally
    required depending on transformation_type — that cross-field
    logic lives in the view, since it depends on combinations of
    fields rather than any single field's own validity.
    """
    file = serializers.FileField()
    nl_prompt = serializers.CharField(max_length=1000)
    target_column = serializers.CharField(max_length=255)
    transformation_type = serializers.ChoiceField(
        choices=Job.TransformationType.choices,
        default=Job.TransformationType.FIND_REPLACE
    )
    replacement_value = serializers.CharField(
        max_length=500, required=False, allow_blank=True
    )
    output_column_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )


class JobSerializer(serializers.ModelSerializer):
    """
    Serializes a Job object going OUT to React.
    """
    class Meta:
        model = Job
        fields = [
            'id',
            'status',
            'progress',
            'nl_prompt',
            'target_column',
            'transformation_type',
            'replacement_value',
            'output_column_name',
            'error_message',
            'created_at',
        ]
        read_only_fields = fields