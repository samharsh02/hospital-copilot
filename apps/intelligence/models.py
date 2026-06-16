from django.conf import settings
from django.db import models

from apps.core.models import BaseMixin
from apps.intelligence.constants import PromptType, RequestStatus


class IntelligenceRequest(BaseMixin):
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="intelligence_requests",
    )
    admission = models.ForeignKey(
        "patients.Admission",
        on_delete=models.CASCADE,
        related_name="intelligence_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="intelligence_requests",
    )
    prompt_type = models.CharField(max_length=30, choices=PromptType.choices)
    status = models.CharField(
        max_length=20,
        choices=RequestStatus.choices,
        default=RequestStatus.PENDING,
    )
    clinical_context_used = models.BooleanField(default=False)
    response_text = models.TextField(null=True, blank=True)
    disclaimer = models.TextField(default="")
    tokens_used = models.IntegerField(null=True, blank=True)
    latency_ms = models.IntegerField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "intelligence_requests"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"IntelligenceRequest #{self.pk} ({self.prompt_type}, {self.status})"
