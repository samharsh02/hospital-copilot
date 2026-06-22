from django.conf import settings
from django.db import models

from apps.communications.constants import NotificationKind
from apps.core.models import BaseMixin


class Notification(BaseMixin):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    hospital = models.ForeignKey(
        "core.Hospital",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    kind = models.CharField(
        max_length=30,
        choices=NotificationKind.choices,
        default=NotificationKind.GENERAL,
    )
    payload = models.JSONField(default=dict)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "read_at"]),
        ]

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
