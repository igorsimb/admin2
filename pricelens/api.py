"""
API views for the Pricelens app.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LogEventSerializer
from .utils import log_investigation_event


class LogEventAPIView(APIView):
    """API view for logging an investigation event."""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = LogEventSerializer(data=request.data)
        if serializer.is_valid():
            log_investigation_event(**serializer.validated_data)
            return Response(status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
