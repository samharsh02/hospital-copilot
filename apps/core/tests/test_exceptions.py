import pytest
from unittest.mock import MagicMock
from rest_framework import status

from apps.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
    custom_exception_handler,
)


class TestAppError:
    def test_default_status_code(self):
        error = AppError("something went wrong")
        assert error.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_default_error_code(self):
        error = AppError("something went wrong")
        assert error.error_code == "INTERNAL_ERROR"

    def test_message_is_stored(self):
        error = AppError("something went wrong")
        assert error.message == "something went wrong"

    def test_custom_error_code_overrides_default(self):
        error = AppError("something went wrong", error_code="CUSTOM_CODE")
        assert error.error_code == "CUSTOM_CODE"

    def test_is_exception(self):
        assert issubclass(AppError, Exception)


class TestNotFoundError:
    def test_status_code(self):
        assert NotFoundError("not found").status_code == status.HTTP_404_NOT_FOUND

    def test_error_code(self):
        assert NotFoundError("not found").error_code == "NOT_FOUND"

    def test_is_app_error(self):
        assert issubclass(NotFoundError, AppError)


class TestPermissionDeniedError:
    def test_status_code(self):
        assert PermissionDeniedError("denied").status_code == status.HTTP_403_FORBIDDEN

    def test_error_code(self):
        assert PermissionDeniedError("denied").error_code == "PERMISSION_DENIED"


class TestValidationError:
    def test_status_code(self):
        assert ValidationError("invalid").status_code == status.HTTP_400_BAD_REQUEST

    def test_error_code(self):
        assert ValidationError("invalid").error_code == "VALIDATION_ERROR"


class TestConflictError:
    def test_status_code(self):
        assert ConflictError("conflict").status_code == status.HTTP_409_CONFLICT

    def test_error_code(self):
        assert ConflictError("conflict").error_code == "CONFLICT"


class TestCustomExceptionHandler:
    def _make_context(self):
        return {"view": MagicMock(), "request": MagicMock()}

    def test_returns_correct_body_for_not_found_error(self):
        response = custom_exception_handler(NotFoundError("Patient not found"), self._make_context())
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"] == "NOT_FOUND"
        assert response.data["message"] == "Patient not found"

    def test_returns_correct_body_for_validation_error(self):
        response = custom_exception_handler(ValidationError("Invalid status"), self._make_context())
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "VALIDATION_ERROR"

    def test_returns_correct_body_for_conflict_error(self):
        response = custom_exception_handler(ConflictError("Already exists"), self._make_context())
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["error"] == "CONFLICT"

    def test_returns_500_for_unhandled_exception(self):
        response = custom_exception_handler(RuntimeError("unexpected"), self._make_context())
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.data["error"] == "INTERNAL_ERROR"

    def test_delegates_drf_exceptions_to_drf_handler(self):
        from rest_framework.exceptions import AuthenticationFailed
        response = custom_exception_handler(AuthenticationFailed("bad token"), self._make_context())
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
