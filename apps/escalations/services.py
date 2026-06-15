from django.utils.timezone import now

from apps.core.exceptions import ConflictError
from apps.core.exceptions import ValidationError as AppValidationError
from apps.escalations.constants import VALID_OPS, AlertStatus
from apps.escalations.models import EscalationAlert, EscalationRule
from apps.events.models import ClinicalEvent
from apps.patients.models import Admission
from apps.users.constants import UserRole


# ---------------------------------------------------------------------------
# Condition DSL
# ---------------------------------------------------------------------------

def _validate_condition(condition: dict) -> None:
    if not isinstance(condition, dict):
        raise AppValidationError("Condition must be an object.")
    for key in ("field", "op", "value"):
        if key not in condition:
            raise AppValidationError(f"Condition must have a '{key}' key.")
    if condition["op"] not in VALID_OPS:
        raise AppValidationError(
            f"Invalid op '{condition['op']}'. Must be one of: {', '.join(sorted(VALID_OPS))}."
        )
    if condition["op"] == "in" and not isinstance(condition["value"], list):
        raise AppValidationError("Value for 'in' operator must be a list.")


def _resolve_field(field_path: str, event: ClinicalEvent):
    """Resolve a dotted field path against a ClinicalEvent.

    Supported roots: payload.<key>[.<key>…], event_type, notes.
    Returns None if the path cannot be resolved.
    """
    parts = field_path.split(".")
    root = parts[0]

    if root == "payload":
        obj = event.payload
        for part in parts[1:]:
            if not isinstance(obj, dict):
                return None
            obj = obj.get(part)
        return obj
    elif root == "event_type":
        return event.event_type
    elif root == "notes":
        return event.notes
    return None


def _evaluate_condition(condition: dict, event: ClinicalEvent) -> bool:
    actual = _resolve_field(condition["field"], event)
    if actual is None:
        return False
    op = condition["op"]
    value = condition["value"]
    try:
        if op == "eq":
            return actual == value
        if op == "ne":
            return actual != value
        if op == "lt":
            return float(actual) < float(value)
        if op == "lte":
            return float(actual) <= float(value)
        if op == "gt":
            return float(actual) > float(value)
        if op == "gte":
            return float(actual) >= float(value)
        if op == "in":
            return actual in value
    except (TypeError, ValueError):
        return False
    return False


# ---------------------------------------------------------------------------
# Rule CRUD
# ---------------------------------------------------------------------------

def get_rule_queryset(*, user):
    qs = EscalationRule.objects.select_related("hospital")
    if user.role != UserRole.SUPERADMIN:
        qs = qs.filter(hospital=user.hospital)
    return qs


def get_alert_queryset(*, user):
    qs = EscalationAlert.objects.select_related(
        "rule", "patient", "admission", "acknowledged_by"
    )
    if user.role != UserRole.SUPERADMIN:
        qs = qs.filter(rule__hospital=user.hospital)
    return qs


def create_rule(
    *,
    user,
    hospital,
    name: str,
    condition: dict,
    priority: str,
    notify_roles: list,
    is_active: bool = True,
) -> EscalationRule:
    _validate_condition(condition)
    return EscalationRule.objects.create(
        hospital=hospital,
        name=name,
        condition=condition,
        priority=priority,
        notify_roles=notify_roles,
        is_active=is_active,
        created_by=user,
        updated_by=user,
    )


def update_rule(*, user, rule: EscalationRule, **kwargs) -> EscalationRule:
    if "condition" in kwargs:
        _validate_condition(kwargs["condition"])
    for field, value in kwargs.items():
        setattr(rule, field, value)
    rule.updated_by = user
    rule.save()
    return rule


# ---------------------------------------------------------------------------
# Rule evaluation (called by Celery task after each clinical event)
# ---------------------------------------------------------------------------

def evaluate_escalation_rules(admission_id: int) -> list[EscalationAlert]:
    try:
        admission = Admission.objects.select_related("patient__hospital").get(pk=admission_id)
    except Admission.DoesNotExist:
        return []

    latest_event = (
        ClinicalEvent.objects.filter(admission=admission)
        .order_by("-recorded_at")
        .first()
    )
    if latest_event is None:
        return []

    rules = EscalationRule.objects.filter(
        hospital=admission.patient.hospital,
        is_active=True,
    )

    created_alerts = []
    for rule in rules:
        if not _evaluate_condition(rule.condition, latest_event):
            continue
        # Dedup: skip if an OPEN alert for this rule+admission already exists
        if EscalationAlert.objects.filter(
            rule=rule, admission=admission, status=AlertStatus.OPEN
        ).exists():
            continue
        alert = EscalationAlert.objects.create(
            rule=rule,
            patient=admission.patient,
            admission=admission,
        )
        _push_alert_notification(alert)
        created_alerts.append(alert)

    return created_alerts


def _push_alert_notification(alert: EscalationAlert) -> None:
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"hospital_{alert.patient.hospital_id}",
            {
                "type": "notify",
                "data": {
                    "kind": "ESCALATION",
                    "alert_id": alert.pk,
                    "patient_id": alert.patient_id,
                    "rule_name": alert.rule.name,
                    "priority": alert.rule.priority,
                    "notify_roles": alert.rule.notify_roles,
                },
            },
        )
    except Exception:
        pass  # WS push is best-effort; must not fail the task


# ---------------------------------------------------------------------------
# Alert state transitions
# ---------------------------------------------------------------------------

def acknowledge_alert(*, user, alert: EscalationAlert) -> EscalationAlert:
    if alert.status != AlertStatus.OPEN:
        raise AppValidationError(
            f"Alert is already {alert.status.lower()} and cannot be acknowledged."
        )
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by = user
    alert.acknowledged_at = now()
    alert.updated_by = user
    alert.save(update_fields=["status", "acknowledged_by", "acknowledged_at", "updated_by"])
    return alert


def resolve_alert(*, user, alert: EscalationAlert) -> EscalationAlert:
    if alert.status == AlertStatus.RESOLVED:
        raise ConflictError("Alert is already resolved.")
    alert.status = AlertStatus.RESOLVED
    alert.resolved_at = now()
    alert.updated_by = user
    alert.save(update_fields=["status", "resolved_at", "updated_by"])
    return alert
