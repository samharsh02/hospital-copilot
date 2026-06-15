import logging
from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, error_code: str | None = None) -> None:
        self.message = message
        if error_code is not None:
            self.error_code = error_code
        super().__init__(message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "PERMISSION_DENIED"


class ValidationError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "VALIDATION_ERROR"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"


def custom_exception_handler(exc: Any, context: Any) -> Response:
    response = exception_handler(exc, context)

    if response is not None:
        return response

    if isinstance(exc, AppError):
        return Response(
            {"error": exc.error_code, "message": exc.message},
            status=exc.status_code,
        )

    logger.error(
        "Unhandled exception in view",
        exc_info=exc,
        extra={"view": str(context.get("view")), "request": str(context.get("request"))},
    )
    return Response(
        {"error": "INTERNAL_ERROR", "message": "An unexpected error occurred."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
