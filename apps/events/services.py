from apps.core.exceptions import ValidationError as AppValidationError
from apps.events.models import ClinicalEvent
from apps.patients.models import Admission, Patient
from apps.users.constants import UserRole


def record_event(
    *,
    user,
    patient: Patient,
    admission: Admission,
    event_type: str,
    payload: dict,
    notes: str = "",
) -> ClinicalEvent:
    if admission.patient_id != patient.pk:
        raise AppValidationError("Admission does not belong to this patient.")
    if admission.discharged_at is not None:
        raise AppValidationError("Cannot record an event for a discharged admission.")

    event = ClinicalEvent.objects.create(
        patient=patient,
        admission=admission,
        event_type=event_type,
        recorded_by=user,
        payload=payload,
        notes=notes,
        created_by=user,
        updated_by=user,
    )

    # Once escalations app is implemented, trigger rule evaluation here:
    # from apps.escalations.tasks import evaluate_escalation_rules
    # evaluate_escalation_rules.delay(admission.pk)

    return event


def get_event_queryset(*, user, patient: Patient | None = None):
    qs = ClinicalEvent.objects.select_related(
        "patient", "admission", "recorded_by"
    )
    if user.role != UserRole.SUPERADMIN:
        qs = qs.filter(patient__hospital=user.hospital)
    if patient is not None:
        qs = qs.filter(patient=patient)
    return qs
