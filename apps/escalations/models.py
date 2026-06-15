from django.conf import settings
from django.db import models

from apps.core.models import BaseMixin, SoftDeleteMixin
from apps.escalations.constants import AlertPriority, AlertStatus


class EscalationRule(BaseMixin, SoftDeleteMixin):
    hospital = models.ForeignKey(
        "core.Hospital",
        on_delete=models.CASCADE,
        related_name="escalation_rules",
    )
    name = models.CharField(max_length=200)
    # {"field": "payload.spo2", "op": "lt", "value": 90}
    condition = models.JSONField()
    priority = models.CharField(max_length=10, choices=AlertPriority.choices)
    # List of role strings, e.g. ["NURSE", "DOCTOR"] — stored as JSON array
    notify_roles = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "escalation_rules"
        ordering = ["priority", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.priority})"


class EscalationAlert(BaseMixin):
    rule = models.ForeignKey(
        EscalationRule,
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="escalation_alerts",
    )
    admission = models.ForeignKey(
        "patients.Admission",
        on_delete=models.CASCADE,
        related_name="escalation_alerts",
    )
    triggered_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=AlertStatus.choices,
        default=AlertStatus.OPEN,
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acknowledged_alerts",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "escalation_alerts"
        ordering = ["-triggered_at"]

    def __str__(self) -> str:
        return f"Alert #{self.pk} [{self.status}] — {self.rule.name}"
