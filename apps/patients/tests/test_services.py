from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.constants import HospitalType
from apps.core.models import Hospital
from apps.core.exceptions import ConflictError, ValidationError as AppValidationError
from apps.patients.constants import Gender
from apps.patients.models import Bed, Patient, Ward
from apps.patients.services import (
    admit_patient,
    create_patient,
    discharge_patient,
    get_patient_queryset,
    update_patient,
)
from apps.users.constants import UserRole

User = get_user_model()


def make_hospital(name="General Hospital"):
    return Hospital.all_objects.create(
        name=name,
        type=HospitalType.PRIVATE_SINGLE,
        city="Delhi",
        state="Delhi",
        bed_count=50,
    )


def make_user(username="staff", role=UserRole.WARD_STAFF, hospital=None):
    return User.objects.create_user(username=username, password="Pass1234!", role=role, hospital=hospital)


def make_patient(hospital, mrn="MRN001", user=None):
    return Patient.objects.create(
        mrn=mrn,
        first_name="Riya",
        last_name="Sharma",
        date_of_birth="1990-01-15",
        gender=Gender.FEMALE,
        hospital=hospital,
    )


def make_ward(hospital):
    return Ward.objects.create(name="Ward A", hospital=hospital, capacity=10)


def make_bed(ward, number="B1"):
    return Bed.objects.create(number=number, ward=ward)


class TestCreatePatient(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)

    def test_creates_patient(self):
        p = create_patient(
            user=self.admin,
            hospital=self.hospital,
            mrn="MRN001",
            first_name="Anita",
            last_name="Rao",
            date_of_birth="1985-06-20",
            gender=Gender.FEMALE,
        )
        self.assertIsNotNone(p.pk)
        self.assertEqual(p.mrn, "MRN001")
        self.assertEqual(p.hospital, self.hospital)

    def test_encrypts_first_name(self):
        p = create_patient(
            user=self.admin,
            hospital=self.hospital,
            mrn="MRN002",
            first_name="Secret",
            last_name="Name",
            date_of_birth="1990-01-01",
            gender=Gender.MALE,
        )
        fresh = Patient.objects.get(pk=p.pk)
        self.assertEqual(fresh.first_name, "Secret")

    def test_duplicate_mrn_same_hospital_raises(self):
        create_patient(
            user=self.admin,
            hospital=self.hospital,
            mrn="MRN003",
            first_name="A",
            last_name="B",
            date_of_birth="1990-01-01",
            gender=Gender.MALE,
        )
        with self.assertRaises(ConflictError):
            create_patient(
                user=self.admin,
                hospital=self.hospital,
                mrn="MRN003",
                first_name="C",
                last_name="D",
                date_of_birth="1990-01-01",
                gender=Gender.MALE,
            )

    def test_same_mrn_different_hospital_ok(self):
        h2 = make_hospital("Another Hospital")
        admin2 = make_user("admin2", UserRole.ADMIN, h2)
        p1 = create_patient(
            user=self.admin, hospital=self.hospital,
            mrn="MRN999", first_name="A", last_name="B",
            date_of_birth="1990-01-01", gender=Gender.MALE,
        )
        p2 = create_patient(
            user=admin2, hospital=h2,
            mrn="MRN999", first_name="C", last_name="D",
            date_of_birth="1990-01-01", gender=Gender.MALE,
        )
        self.assertNotEqual(p1.pk, p2.pk)

    def test_sets_created_by(self):
        p = create_patient(
            user=self.admin, hospital=self.hospital,
            mrn="MRN004", first_name="A", last_name="B",
            date_of_birth="1990-01-01", gender=Gender.MALE,
        )
        self.assertEqual(p.created_by, self.admin)

    def test_optional_fields_default_to_empty(self):
        p = create_patient(
            user=self.admin, hospital=self.hospital,
            mrn="MRN005", first_name="A", last_name="B",
            date_of_birth="1990-01-01", gender=Gender.MALE,
        )
        self.assertEqual(p.blood_group, "")
        self.assertEqual(p.contact_phone, "")
        self.assertEqual(p.emergency_contact_name, "")


class TestAdmitPatient(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.ward = make_ward(self.hospital)
        self.bed = make_bed(self.ward)

    def test_admit_without_bed(self):
        admission = admit_patient(user=self.nurse, patient=self.patient)
        self.assertIsNotNone(admission.pk)
        self.assertIsNone(admission.bed)
        self.assertTrue(admission.is_active)

    def test_admit_with_bed(self):
        admission = admit_patient(user=self.nurse, patient=self.patient, bed=self.bed)
        self.bed.refresh_from_db()
        self.assertTrue(self.bed.is_occupied)
        self.assertEqual(admission.bed, self.bed)

    def test_admit_already_admitted_raises(self):
        admit_patient(user=self.nurse, patient=self.patient)
        with self.assertRaises(AppValidationError):
            admit_patient(user=self.nurse, patient=self.patient)

    def test_admit_occupied_bed_raises(self):
        self.bed.is_occupied = True
        self.bed.save()
        with self.assertRaises(ConflictError):
            admit_patient(user=self.nurse, patient=self.patient, bed=self.bed)

    def test_admit_bed_different_hospital_raises(self):
        h2 = make_hospital("Other Hospital")
        ward2 = make_ward(h2)
        bed2 = make_bed(ward2, "B2")
        with self.assertRaises(AppValidationError):
            admit_patient(user=self.nurse, patient=self.patient, bed=bed2)

    def test_sets_admitted_by(self):
        admission = admit_patient(user=self.nurse, patient=self.patient)
        self.assertEqual(admission.admitted_by, self.nurse)

    def test_notes_stored(self):
        admission = admit_patient(user=self.nurse, patient=self.patient, notes="Routine check")
        self.assertEqual(admission.notes, "Routine check")


class TestDischargePatient(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.nurse = make_user("nurse2", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.ward = make_ward(self.hospital)
        self.bed = make_bed(self.ward)

    def test_discharge_clears_bed(self):
        admit_patient(user=self.nurse, patient=self.patient, bed=self.bed)
        discharge_patient(user=self.nurse, patient=self.patient)
        self.bed.refresh_from_db()
        self.assertFalse(self.bed.is_occupied)

    def test_discharge_sets_discharged_at(self):
        admit_patient(user=self.nurse, patient=self.patient)
        admission = discharge_patient(user=self.nurse, patient=self.patient)
        self.assertIsNotNone(admission.discharged_at)
        self.assertFalse(admission.is_active)

    def test_discharge_not_admitted_raises(self):
        with self.assertRaises(AppValidationError):
            discharge_patient(user=self.nurse, patient=self.patient)

    def test_can_readmit_after_discharge(self):
        admit_patient(user=self.nurse, patient=self.patient)
        discharge_patient(user=self.nurse, patient=self.patient)
        bed2 = make_bed(self.ward, "B2")
        admission2 = admit_patient(user=self.nurse, patient=self.patient, bed=bed2)
        self.assertTrue(admission2.is_active)


class TestGetPatientQueryset(TestCase):
    def setUp(self):
        self.h1 = make_hospital("H1")
        self.h2 = make_hospital("H2")
        self.user1 = make_user("u1", UserRole.NURSE, self.h1)
        self.user2 = make_user("u2", UserRole.NURSE, self.h2)
        self.superadmin = make_user("su", UserRole.SUPERADMIN)
        self.p1 = make_patient(self.h1, "MRN-H1")
        self.p2 = make_patient(self.h2, "MRN-H2")

    def test_scoped_to_own_hospital(self):
        qs = get_patient_queryset(user=self.user1)
        self.assertIn(self.p1, qs)
        self.assertNotIn(self.p2, qs)

    def test_superadmin_sees_all(self):
        qs = get_patient_queryset(user=self.superadmin)
        self.assertIn(self.p1, qs)
        self.assertIn(self.p2, qs)
