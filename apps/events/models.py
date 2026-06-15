from django.conf import settings
from django.db import models
from django.utils.timezone import now

from apps.core.models import BaseMixin
from apps.events.constants import EventType


class ClinicalEvent(BaseMixin):
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="events",
    )
    admission = models.ForeignKey(
        "patients.Admission",
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recorded_events",
    )
    recorded_at = models.DateTimeField(default=now, db_index=True)
    payload = models.JSONField(default=dict)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "clinical_events"
        ordering = ["-recorded_at"]

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.recorded_at:%Y-%m-%d %H:%M}"
