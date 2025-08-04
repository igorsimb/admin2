"""
Serializers for the Pricelens API.
"""

from rest_framework import serializers


class LogEventSerializer(serializers.Serializer):
    """Serializer for the log_event endpoint."""

    event_dt = serializers.DateTimeField()
    supid = serializers.IntegerField()
    reason = serializers.CharField(max_length=100)
    stage = serializers.CharField(max_length=100)
    file_path = serializers.CharField(allow_blank=True)
