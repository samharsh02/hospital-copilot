from django.db import models


class PromptType(models.TextChoices):
    PATIENT_SUMMARY = "PATIENT_SUMMARY", "Patient Summary"
    DISCHARGE_READINESS = "DISCHARGE_READINESS", "Discharge Readiness"
    RISK_FLAG = "RISK_FLAG", "Risk Flag"
    CLINICAL_SUMMARY = "CLINICAL_SUMMARY", "Clinical Summary"


# These types need clinical events to be meaningful — blocked when clinical module is off.
CLINICAL_ONLY_PROMPT_TYPES = {PromptType.RISK_FLAG, PromptType.CLINICAL_SUMMARY}


class RequestStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


DISCLAIMER = (
    "IMPORTANT: This output is AI-generated decision support only. "
    "It is NOT a clinical directive, NOT a diagnosis, and NOT a prescription. "
    "All observations must be independently reviewed by a qualified clinician "
    "before any clinical action is taken."
)
