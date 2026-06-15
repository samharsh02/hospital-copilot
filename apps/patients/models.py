from django.conf import settings
from django.db import models
from encrypted_model_fields.fields import EncryptedCharField

from apps.core.models import BaseMixin, SoftDeleteMixin
from apps.patients.constants import BloodGroup, Gender


class Patient(BaseMixin, SoftDeleteMixin):
    mrn = models.CharField(max_length=50)
    first_name = EncryptedCharField(max_length=150)
    last_name = EncryptedCharField(max_length=150)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=Gender.choices)
    blood_group = models.CharField(max_length=5, choices=BloodGroup.choices, blank=True, default="")
    contact_phone = EncryptedCharField(max_length=20, blank=True, default="")
    emergency_contact_name = models.CharField(max_length=200, blank=True, default="")
    emergency_contact_phone = EncryptedCharField(max_length=20, blank=True, default="")
    hospital = models.ForeignKey(
        "core.Hospital",
        on_delete=models.CASCADE,
        related_name="patients",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "patients"
        unique_together = [("hospital", "mrn")]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.mrn


class Ward(BaseMixin, SoftDeleteMixin):
    name = models.CharField(max_length=100)
    hospital = models.ForeignKey(
        "core.Hospital",
        on_delete=models.CASCADE,
        related_name="wards",
    )
    capacity = models.PositiveIntegerField()

    class Meta:
        db_table = "wards"

    def __str__(self) -> str:
        return self.name


class Bed(BaseMixin):
    number = models.CharField(max_length=20)
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="beds")
    is_occupied = models.BooleanField(default=False)

    class Meta:
        db_table = "beds"
        unique_together = [("ward", "number")]

    def __str__(self) -> str:
        return f"{self.ward}/{self.number}"


class Admission(BaseMixin):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="admissions")
    bed = models.ForeignKey(
        Bed,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admissions",
    )
    admitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admissions_made",
    )
    admitted_at = models.DateTimeField()
    discharged_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "admissions"

    def __str__(self) -> str:
        return f"Admission #{self.pk}"

    @property
    def is_active(self) -> bool:
        return self.discharged_at is None
