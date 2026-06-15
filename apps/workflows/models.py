from django.conf import settings
from django.db import models

from apps.core.models import BaseMixin, SoftDeleteMixin
from apps.workflows.constants import InstanceStatus, WorkflowTrigger


class WorkflowTemplate(BaseMixin, SoftDeleteMixin):
    name = models.CharField(max_length=200)
    hospital = models.ForeignKey(
        "core.Hospital",
        on_delete=models.CASCADE,
        related_name="workflow_templates",
    )
    # Array of {index: int, title: str, description: str}
    steps = models.JSONField(default=list)
    trigger = models.CharField(max_length=20, choices=WorkflowTrigger.choices, default=WorkflowTrigger.MANUAL)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "workflow_templates"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WorkflowInstance(BaseMixin):
    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.CASCADE,
        related_name="instances",
    )
    admission = models.ForeignKey(
        "patients.Admission",
        on_delete=models.CASCADE,
        related_name="workflow_instances",
    )
    status = models.CharField(
        max_length=20,
        choices=InstanceStatus.choices,
        default=InstanceStatus.PENDING,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_workflow_instances",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "workflow_instances"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Instance #{self.pk} ({self.status})"


class WorkflowStep(BaseMixin):
    instance = models.ForeignKey(
        WorkflowInstance,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    step_index = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    is_completed = models.BooleanField(default=False)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completed_workflow_steps",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "workflow_steps"
        unique_together = [("instance", "step_index")]
        ordering = ["step_index"]

    def __str__(self) -> str:
        return f"Step {self.step_index}: {self.title}"
