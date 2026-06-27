from rest_framework import serializers
from .models import Job


class JobCreateSerializer(serializers.Serializer):
    """
    Validates the data coming IN from React when creating a job.
    We use a plain Serializer (not ModelSerializer) because the
    request includes a file upload, which needs special handling.
    """
    file = serializers.FileField()
    nl_prompt = serializers.CharField(max_length=1000)
    target_column = serializers.CharField(max_length=255)
    replacement_value = serializers.CharField(max_length=500)


class JobSerializer(serializers.ModelSerializer):
    """
    Serializes a Job object going OUT to React.
    Controls exactly which fields React can see.
    """
    class Meta:
        model = Job
        fields = [
            'id',
            'status',
            'progress',
            'nl_prompt',
            'target_column',
            'replacement_value',
            'error_message',
            'created_at',
        ]
        # These fields can never be set by the client
        read_only_fields = fields