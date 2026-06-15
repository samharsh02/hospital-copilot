from django.contrib.auth import get_user_model

from apps.core.exceptions import ConflictError
from apps.core.models import Hospital
from apps.users.constants import UserRole

User = get_user_model()


def register_user(
    *,
    username: str,
    email: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
    role: str = UserRole.WARD_STAFF,
    hospital: Hospital | None = None,
    phone: str = "",
) -> "User":
    if User.objects.filter(username=username).exists():
        raise ConflictError("Username already taken.")
    if email and User.objects.filter(email=email).exists():
        raise ConflictError("Email already registered.")
    return User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        role=role,
        hospital=hospital,
        phone=phone,
    )
