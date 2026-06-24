from django.utils.timezone import now

from apps.core.exceptions import ConflictError
from apps.core.exceptions import ValidationError as AppValidationError
from apps.core.models import Hospital
from apps.patients.models import Admission, Bed, Patient, Ward
from apps.users.constants import UserRole


def get_patient_queryset(*, user):
    qs = Patient.objects.select_related("hospital")
    if user.role != UserRole.SUPERADMIN:
        qs = qs.filter(hospital=user.hospital)
    return qs


def create_patient(
    *,
    user,
    hospital: Hospital,
    mrn: str,
    first_name: str,
    last_name: str,
    date_of_birth,
    gender: str,
    blood_group: str = "",
    contact_phone: str = "",
    emergency_contact_name: str = "",
    emergency_contact_phone: str = "",
) -> Patient:
    if Patient.objects.filter(hospital=hospital, mrn=mrn).exists():
        raise ConflictError(f"MRN '{mrn}' already exists in this hospital.")
    return Patient.objects.create(
        mrn=mrn,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date_of_birth,
        gender=gender,
        blood_group=blood_group,
        contact_phone=contact_phone,
        emergency_contact_name=emergency_contact_name,
        emergency_contact_phone=emergency_contact_phone,
        hospital=hospital,
        created_by=user,
        updated_by=user,
    )


def update_patient(*, user, patient: Patient, **kwargs) -> Patient:
    for field, value in kwargs.items():
        setattr(patient, field, value)
    patient.updated_by = user
    patient.save()
    return patient


def admit_patient(
    *,
    user,
    patient: Patient,
    bed: Bed | None = None,
    notes: str = "",
) -> Admission:
    if patient.admissions.filter(discharged_at__isnull=True).exists():
        raise AppValidationError("Patient already has an active admission.")
    if bed is not None:
        if bed.is_occupied:
            raise ConflictError("Bed is already occupied.")
        if bed.ward.hospital_id != patient.hospital_id:
            raise AppValidationError("Bed does not belong to the patient's hospital.")
    admission = Admission.objects.create(
        patient=patient,
        bed=bed,
        admitted_by=user,
        admitted_at=now(),
        notes=notes,
        created_by=user,
        updated_by=user,
    )
    if bed is not None:
        bed.is_occupied = True
        bed.save(update_fields=["is_occupied"])
    return admission


def get_ward_queryset(*, user):
    if user.role == UserRole.SUPERADMIN:
        return Ward.objects.select_related("hospital").all()
    return Ward.objects.filter(hospital=user.hospital)


def create_ward(*, user, hospital, name: str, capacity: int) -> Ward:
    return Ward.objects.create(
        name=name,
        hospital=hospital,
        capacity=capacity,
        created_by=user,
        updated_by=user,
    )


def update_ward(*, user, ward: Ward, **kwargs) -> Ward:
    for field, value in kwargs.items():
        setattr(ward, field, value)
    ward.updated_by = user
    ward.save()
    return ward


def create_bed(*, user, ward: Ward, number: str) -> Bed:
    if Bed.objects.filter(ward=ward, number=number).exists():
        raise ConflictError(f"Bed '{number}' already exists in this ward.")
    return Bed.objects.create(
        number=number,
        ward=ward,
        created_by=user,
        updated_by=user,
    )


def update_bed(*, user, bed: Bed, **kwargs) -> Bed:
    for field, value in kwargs.items():
        setattr(bed, field, value)
    bed.updated_by = user
    bed.save()
    return bed


def delete_bed(*, user, bed: Bed) -> None:
    if bed.is_occupied:
        raise AppValidationError("Cannot delete an occupied bed.")
    bed.delete()


def discharge_patient(*, user, patient: Patient) -> Admission:
    try:
        admission = patient.admissions.select_related("bed").get(discharged_at__isnull=True)
    except Admission.DoesNotExist:
        raise AppValidationError("Patient has no active admission.")
    admission.discharged_at = now()
    admission.updated_by = user
    admission.save(update_fields=["discharged_at", "updated_by"])
    if admission.bed is not None:
        admission.bed.is_occupied = False
        admission.bed.save(update_fields=["is_occupied"])
    return admission
