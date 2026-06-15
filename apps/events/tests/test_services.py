from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from apps.core.constants import HospitalType
from apps.core.exceptions import ValidationError as AppValidationError
from apps.core.models import Hospital
from apps.events.constants import EventType
from apps.events.models import ClinicalEvent
from apps.events.services import get_event_queryset, record_event
from apps.patients.constants import Gender
from apps.patients.models import Admission, Patient
from apps.users.constants import UserRole

User = get_user_model()

VITALS_PAYLOAD = {"temperature": 37.2, "bp": "120/80", "pulse": 72}


def make_hospital(name="General Hospital"):
    return Hospital.all_objects.create(
        name=name, type=HospitalType.PRIVATE_SINGLE,
        city="Delhi", state="Delhi", bed_count=50,
    )


def make_user(username="nurse1", role=UserRole.NURSE, hospital=None):
    return User.objects.create_user(username=username, password="Pass1234!", role=role, hospital=hospital)


def make_patient(hospital, mrn="MRN001"):
    return Patient.objects.create(
        mrn=mrn, first_name="Riya", last_name="Sharma",
        date_of_birth="1990-01-15", gender=Gender.FEMALE, hospital=hospital,
    )


def make_admission(patient, user):
    return Admission.objects.create(
        patient=patient, admitted_at=now(), admitted_by=user,
        created_by=user, updated_by=user,
    )


# ---------- record_event ----------

class TestRecordEvent(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.nurse)

    def test_creates_event(self):
        event = record_event(
            user=self.nurse, patient=self.patient, admission=self.admission,
            event_type=EventType.VITALS, payload=VITALS_PAYLOAD,
        )
        self.assertIsInstance(event, ClinicalEvent)
        self.assertEqual(event.event_type, EventType.VITALS)
        self.assertEqual(event.patient, self.patient)
        self.assertEqual(event.admission, self.admission)
        self.assertEqual(event.recorded_by, self.nurse)
        self.assertEqual(event.payload, VITALS_PAYLOAD)

    def test_notes_saved(self):
        event = record_event(
            user=self.nurse, patient=self.patient, admission=self.admission,
            event_type=EventType.NURSE_NOTE, payload={}, notes="Patient comfortable.",
        )
        self.assertEqual(event.notes, "Patient comfortable.")

    def test_empty_payload_defaults_to_dict(self):
        event = record_event(
            user=self.nurse, patient=self.patient, admission=self.admission,
            event_type=EventType.OTHER, payload={},
        )
        self.assertEqual(event.payload, {})

    def test_wrong_patient_raises(self):
        other_patient = make_patient(self.hospital, mrn="MRN002")
        with self.assertRaises(AppValidationError):
            record_event(
                user=self.nurse, patient=other_patient, admission=self.admission,
                event_type=EventType.VITALS, payload=VITALS_PAYLOAD,
            )

    def test_discharged_admission_raises(self):
        self.admission.discharged_at = now()
        self.admission.save(update_fields=["discharged_at"])
        with self.assertRaises(AppValidationError):
            record_event(
                user=self.nurse, patient=self.patient, admission=self.admission,
                event_type=EventType.VITALS, payload=VITALS_PAYLOAD,
            )

    def test_all_event_types_accepted(self):
        for event_type in EventType.values:
            event = record_event(
                user=self.nurse, patient=self.patient, admission=self.admission,
                event_type=event_type, payload={},
            )
            self.assertEqual(event.event_type, event_type)


# ---------- get_event_queryset ----------

class TestGetEventQueryset(TestCase):
    def setUp(self):
        self.h1 = make_hospital("H1")
        self.h2 = make_hospital("H2")
        self.nurse1 = make_user("nurse1", UserRole.NURSE, self.h1)
        self.nurse2 = make_user("nurse2", UserRole.NURSE, self.h2)
        self.superadmin = make_user("sa", UserRole.SUPERADMIN)

        p1 = make_patient(self.h1)
        a1 = make_admission(p1, self.nurse1)
        record_event(user=self.nurse1, patient=p1, admission=a1, event_type=EventType.VITALS, payload={})
        record_event(user=self.nurse1, patient=p1, admission=a1, event_type=EventType.MEDICATION, payload={})

        p2 = make_patient(self.h2, mrn="MRN-H2")
        a2 = make_admission(p2, self.nurse2)
        record_event(user=self.nurse2, patient=p2, admission=a2, event_type=EventType.VITALS, payload={})

        self.p1, self.a1 = p1, a1

    def test_non_superadmin_sees_own_hospital_events(self):
        qs = get_event_queryset(user=self.nurse1)
        self.assertEqual(qs.count(), 2)

    def test_superadmin_sees_all_events(self):
        qs = get_event_queryset(user=self.superadmin)
        self.assertEqual(qs.count(), 3)

    def test_filter_by_patient(self):
        qs = get_event_queryset(user=self.nurse1, patient=self.p1)
        self.assertEqual(qs.count(), 2)

    def test_other_hospital_patient_returns_nothing(self):
        p2 = make_patient(self.h2, mrn="MRN-X")
        qs = get_event_queryset(user=self.nurse1, patient=p2)
        self.assertEqual(qs.count(), 0)
