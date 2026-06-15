from django.utils.timezone import now

from apps.core.exceptions import ConflictError
from apps.core.exceptions import ValidationError as AppValidationError
from apps.core.models import Hospital
from apps.patients.models import Admission
from apps.users.constants import UserRole
from apps.workflows.constants import InstanceStatus
from apps.workflows.models import WorkflowInstance, WorkflowStep, WorkflowTemplate


def _validate_steps(steps) -> None:
    if not isinstance(steps, list) or not steps:
        raise AppValidationError("Steps must be a non-empty list.")
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise AppValidationError(f"Step {i} must be an object.")
        if "index" not in step:
            raise AppValidationError(f"Step {i} must have an 'index' field.")
        if "title" not in step:
            raise AppValidationError(f"Step {i} must have a 'title' field.")
        if not isinstance(step["title"], str) or not step["title"].strip():
            raise AppValidationError(f"Step {i} title must be a non-empty string.")


def get_template_queryset(*, user):
    qs = WorkflowTemplate.objects.select_related("hospital")
    if user.role != UserRole.SUPERADMIN:
        qs = qs.filter(hospital=user.hospital)
    return qs


def get_instance_queryset(*, user):
    qs = WorkflowInstance.objects.select_related("template", "admission", "assigned_to")
    if user.role != UserRole.SUPERADMIN:
        qs = qs.filter(template__hospital=user.hospital)
    return qs


def create_template(
    *,
    user,
    hospital: Hospital,
    name: str,
    steps: list,
    trigger: str,
    is_active: bool = True,
) -> WorkflowTemplate:
    _validate_steps(steps)
    return WorkflowTemplate.objects.create(
        name=name,
        hospital=hospital,
        steps=steps,
        trigger=trigger,
        is_active=is_active,
        created_by=user,
        updated_by=user,
    )


def update_template(*, user, template: WorkflowTemplate, **kwargs) -> WorkflowTemplate:
    if "steps" in kwargs:
        _validate_steps(kwargs["steps"])
    for field, value in kwargs.items():
        setattr(template, field, value)
    template.updated_by = user
    template.save()
    return template


def start_workflow(
    *,
    user,
    template: WorkflowTemplate,
    admission: Admission,
    assigned_to=None,
) -> WorkflowInstance:
    if template.hospital_id != admission.patient.hospital_id:
        raise AppValidationError("Template and admission belong to different hospitals.")
    if not template.is_active:
        raise AppValidationError("Cannot start an instance from an inactive template.")
    if admission.discharged_at is not None:
        raise AppValidationError("Cannot start a workflow for a discharged admission.")

    instance = WorkflowInstance.objects.create(
        template=template,
        admission=admission,
        status=InstanceStatus.PENDING,
        assigned_to=assigned_to,
        created_by=user,
        updated_by=user,
    )

    WorkflowStep.objects.bulk_create([
        WorkflowStep(
            instance=instance,
            step_index=step["index"],
            title=step["title"],
            created_by=user,
            updated_by=user,
        )
        for step in sorted(template.steps, key=lambda s: s["index"])
    ])

    return instance


def complete_step(*, user, instance: WorkflowInstance, step_index: int, notes: str = "") -> WorkflowStep:
    if instance.status == InstanceStatus.COMPLETED:
        raise AppValidationError("This workflow instance is already completed.")
    if instance.status == InstanceStatus.CANCELLED:
        raise AppValidationError("Cannot complete a step on a cancelled workflow.")

    try:
        step = instance.steps.get(step_index=step_index)
    except WorkflowStep.DoesNotExist:
        raise AppValidationError(f"Step {step_index} does not exist on this instance.")

    if step.is_completed:
        raise ConflictError(f"Step {step_index} is already completed.")

    step.is_completed = True
    step.completed_by = user
    step.completed_at = now()
    step.notes = notes
    step.updated_by = user
    step.save(update_fields=["is_completed", "completed_by", "completed_at", "notes", "updated_by"])

    ts = now()
    if instance.status == InstanceStatus.PENDING:
        instance.status = InstanceStatus.IN_PROGRESS
        instance.started_at = ts
        instance.updated_by = user
        instance.save(update_fields=["status", "started_at", "updated_by"])

    all_done = not instance.steps.filter(is_completed=False).exists()
    if all_done:
        instance.status = InstanceStatus.COMPLETED
        instance.completed_at = ts
        instance.updated_by = user
        instance.save(update_fields=["status", "completed_at", "updated_by"])

    return step


def cancel_workflow(*, user, instance: WorkflowInstance) -> WorkflowInstance:
    if instance.status in (InstanceStatus.COMPLETED, InstanceStatus.CANCELLED):
        raise AppValidationError(f"Cannot cancel a workflow in '{instance.status}' status.")
    instance.status = InstanceStatus.CANCELLED
    instance.updated_by = user
    instance.save(update_fields=["status", "updated_by"])
    return instance
