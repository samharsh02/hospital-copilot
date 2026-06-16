import time

import anthropic
from django.conf import settings
from django.utils.timezone import now

from apps.core.exceptions import ValidationError as AppValidationError
from apps.intelligence.constants import (
    CLINICAL_ONLY_PROMPT_TYPES,
    DISCLAIMER,
    PromptType,
    RequestStatus,
)
from apps.intelligence.models import IntelligenceRequest
from apps.users.constants import UserRole


# ---------------------------------------------------------------------------
# Queryset
# ---------------------------------------------------------------------------

def get_request_queryset(*, user):
    qs = IntelligenceRequest.objects.select_related(
        "patient", "admission", "requested_by"
    )
    if user.role != UserRole.SUPERADMIN:
        qs = qs.filter(patient__hospital=user.hospital)
    return qs


# ---------------------------------------------------------------------------
# Request creation
# ---------------------------------------------------------------------------

def request_ai_query(*, user, patient, admission, prompt_type) -> IntelligenceRequest:
    hospital = patient.hospital
    if prompt_type in CLINICAL_ONLY_PROMPT_TYPES and not hospital.clinical_module_enabled:
        raise AppValidationError(
            f"Prompt type '{prompt_type}' requires the clinical module to be enabled for this hospital."
        )
    req = IntelligenceRequest.objects.create(
        patient=patient,
        admission=admission,
        requested_by=user,
        prompt_type=prompt_type,
        status=RequestStatus.PENDING,
        created_by=user,
        updated_by=user,
    )
    from apps.intelligence.tasks import run_ai_query_task
    run_ai_query_task.delay(req.pk)
    return req


# ---------------------------------------------------------------------------
# Prompt building (two-tier context)
# ---------------------------------------------------------------------------

def _build_tier1_context(admission) -> str:
    import datetime
    patient = admission.patient
    today = now().date()
    dob = patient.date_of_birth
    # Django doesn't call to_python() for in-memory objects created via .create(**kwargs),
    # so date_of_birth may be a string "YYYY-MM-DD" rather than a datetime.date.
    if isinstance(dob, str):
        dob = datetime.date.fromisoformat(dob)
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    los_days = (now() - admission.admitted_at).days

    ward_info = "No ward assigned"
    bed_info = "No bed assigned"
    if admission.bed_id and admission.bed:
        bed_info = f"Bed {admission.bed.number}"
        ward_info = admission.bed.ward.name if hasattr(admission.bed, "ward") else "Unknown ward"

    lines = [
        f"PATIENT: MRN {patient.mrn}, Age {age}, Gender {patient.gender}",
        f"ADMISSION: Admitted {admission.admitted_at.strftime('%Y-%m-%d %H:%M')}, Day {los_days + 1} of admission",
        f"LOCATION: {ward_info}, {bed_info}",
    ]
    if admission.discharged_at:
        lines.append(f"DISCHARGE: Patient discharged {admission.discharged_at.strftime('%Y-%m-%d %H:%M')}")
    if admission.notes:
        lines.append(f"ADMISSION NOTES: {admission.notes}")
    return "\n".join(lines)


def _build_tier2_context(admission) -> str:
    from apps.escalations.constants import AlertStatus
    from apps.escalations.models import EscalationAlert
    from apps.events.models import ClinicalEvent

    events = (
        ClinicalEvent.objects.filter(admission=admission)
        .select_related("recorded_by")
        .order_by("recorded_at")[:20]
    )

    lines = []
    if events:
        lines.append("CLINICAL EVENTS (up to last 20, chronological):")
        for e in events:
            recorder = e.recorded_by.username if e.recorded_by else "unknown"
            payload_str = (
                ", ".join(f"{k}={v}" for k, v in e.payload.items())
                if e.payload else "no payload"
            )
            line = f"  [{e.recorded_at.strftime('%Y-%m-%d %H:%M')}] {e.event_type} by {recorder}: {payload_str}"
            if e.notes:
                line += f" — {e.notes}"
            lines.append(line)
    else:
        lines.append("CLINICAL EVENTS: No clinical events recorded for this admission.")

    open_alerts = EscalationAlert.objects.filter(
        admission=admission, status=AlertStatus.OPEN
    ).select_related("rule")
    if open_alerts.exists():
        lines.append("OPEN ESCALATION ALERTS:")
        for alert in open_alerts:
            lines.append(
                f"  [{alert.triggered_at.strftime('%Y-%m-%d %H:%M')}] "
                f"{alert.rule.name} — Priority: {alert.rule.priority}"
            )
    else:
        lines.append("OPEN ESCALATION ALERTS: None.")

    return "\n".join(lines)


_INSTRUCTIONS = {
    PromptType.PATIENT_SUMMARY: (
        "Provide a concise summary of this patient's current admission status. "
        "Include the length of stay, location, and any notable clinical context if available. "
        "If clinical data is absent, summarise the operational picture only."
    ),
    PromptType.DISCHARGE_READINESS: (
        "Assess whether this patient appears ready for discharge based on available data. "
        "Consider length of stay, open alerts, and clinical events if available. "
        "Flag any concerns that would delay discharge. "
        "If clinical data is absent, base your assessment on length of stay and operational data only."
    ),
    PromptType.RISK_FLAG: (
        "Review the clinical events and open alerts for this patient. "
        "Identify any patterns or values that may warrant immediate clinical attention. "
        "If there is insufficient clinical data, say so explicitly — do not speculate."
    ),
    PromptType.CLINICAL_SUMMARY: (
        "Synthesise the clinical events for this patient into a clear narrative for the treating doctor. "
        "Present findings chronologically, highlight trends, and note any unresolved alerts. "
        "If there is insufficient clinical data, say so explicitly — do not speculate."
    ),
}

_SYSTEM_PROMPT = (
    "You are a hospital decision-support assistant. You analyse patient data and provide "
    "factual, cautious observations to help clinical and administrative staff. "
    "You never diagnose, prescribe, or speculate beyond available data. "
    "You always recommend that a qualified clinician reviews your output before any action is taken."
)


def build_prompt(request: IntelligenceRequest) -> tuple[str, bool]:
    """Returns (prompt_text, clinical_context_used)."""
    admission = request.admission
    hospital = admission.patient.hospital
    clinical_context_used = hospital.clinical_module_enabled

    tier1 = _build_tier1_context(admission)
    tier2 = _build_tier2_context(admission) if clinical_context_used else None

    instruction = _INSTRUCTIONS.get(
        request.prompt_type,
        "Summarise what is known about this patient's current admission.",
    )

    sections = ["--- PATIENT CONTEXT ---", tier1, ""]
    if tier2:
        sections += ["--- CLINICAL DATA ---", tier2, ""]
    else:
        sections += [
            "--- CLINICAL DATA ---",
            "Clinical module not enabled for this hospital. Only operational data is available.",
            "",
        ]
    sections += [
        "--- TASK ---",
        instruction,
        "",
        "Rules: Do NOT diagnose. Do NOT prescribe. Do NOT speculate beyond what the data shows. "
        "If data is insufficient for the requested analysis, state that clearly.",
    ]
    return "\n".join(sections), clinical_context_used


# ---------------------------------------------------------------------------
# AI execution (called by Celery task)
# ---------------------------------------------------------------------------

def run_ai_query(request_id: int) -> None:
    try:
        req = IntelligenceRequest.objects.select_related(
            "patient__hospital",
            "admission__bed__ward",
            "admission__patient",
        ).get(pk=request_id)
    except IntelligenceRequest.DoesNotExist:
        return

    if req.status != RequestStatus.PENDING:
        return

    prompt_text, clinical_context_used = build_prompt(req)

    start = time.monotonic()
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt_text}],
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    req.status = RequestStatus.COMPLETED
    req.response_text = message.content[0].text
    req.disclaimer = DISCLAIMER
    req.clinical_context_used = clinical_context_used
    req.tokens_used = message.usage.input_tokens + message.usage.output_tokens
    req.latency_ms = latency_ms
    req.completed_at = now()
    req.save(update_fields=[
        "status", "response_text", "disclaimer", "clinical_context_used",
        "tokens_used", "latency_ms", "completed_at",
    ])
    _push_intelligence_notification(req)


def mark_request_failed(request_id: int) -> None:
    IntelligenceRequest.objects.filter(pk=request_id).update(
        status=RequestStatus.FAILED,
        completed_at=now(),
    )


def _push_intelligence_notification(req: IntelligenceRequest) -> None:
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"hospital_{req.patient.hospital_id}",
            {
                "type": "notify",
                "data": {
                    "kind": "INTELLIGENCE_COMPLETE",
                    "request_id": req.pk,
                    "requested_by_id": req.requested_by_id,
                    "status": req.status,
                    "prompt_type": req.prompt_type,
                },
            },
        )
    except Exception:
        pass
