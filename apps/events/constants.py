from django.db import models


class EventType(models.TextChoices):
    VITALS = "VITALS", "Vitals"
    MEDICATION = "MEDICATION", "Medication"
    NURSE_NOTE = "NURSE_NOTE", "Nurse Note"
    DOCTOR_NOTE = "DOCTOR_NOTE", "Doctor Note"
    LAB_RESULT = "LAB_RESULT", "Lab Result"
    ALERT = "ALERT", "Alert"
    OTHER = "OTHER", "Other"
