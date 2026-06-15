from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.users.constants import UserRole


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.WARD_STAFF)
    hospital = models.ForeignKey(
        "core.Hospital",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )
    phone = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        db_table = "users"
