from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Wraps DRF's default exception handler. If DRF already produced a
    response (validation errors, 404s, etc.), we pass it through.
    If DRF couldn't handle it (an unexpected server error), we catch
    it here and always return JSON, never Django's default HTML page.
    """
    response = exception_handler(exc, context)

    if response is not None:
        return response

    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return Response(
        {'error': 'An unexpected server error occurred. Please try again.'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )