from django.contrib.auth import get_user_model
from django.utils.timezone import now
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.constants import HospitalType
from apps.core.models import Hospital
from apps.events.constants import EventType
from apps.events.services import record_event
from apps.patients.constants import Gender
from apps.patients.models import Admission, Patient
from apps.users.constants import UserRole

User = get_user_model()

VITALS = {"temperature": 37.0, "bp": "118/76", "pulse": 68}


def make_hospital(name="City Hospital"):
    return Hospital.all_objects.create(
        name=name, type=HospitalType.PRIVATE_SINGLE,
        city="Mumbai", state="Maharashtra", bed_count=100,
    )


def make_user(username, role=UserRole.NURSE, hospital=None, password="Pass1234!"):
    return User.objects.create_user(username=username, password=password, role=role, hospital=hospital)


def make_patient(hospital, mrn="MRN001"):
    return Patient.objects.create(
        mrn=mrn, first_name="Anita", last_name="Rao",
        date_of_birth="1990-06-15", gender=Gender.FEMALE, hospital=hospital,
    )


def make_admission(patient, user):
    return Admission.objects.create(
        patient=patient, admitted_at=now(), admitted_by=user,
        created_by=user, updated_by=user,
    )


def auth_client(user):
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


# ---------- POST /events/ ----------

class TestRecordEventView(APITestCase):
    url = "/api/v1/events/"

    def setUp(self):
        self.hospital = make_hospital()
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.ward_staff = make_user("ws1", UserRole.WARD_STAFF, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.nurse)

    def test_nurse_records_event(self):
        client = auth_client(self.nurse)
        resp = client.post(self.url, {
            "patient": self.patient.pk,
            "admission": self.admission.pk,
            "event_type": EventType.VITALS,
            "payload": VITALS,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["event_type"], EventType.VITALS)
        self.assertEqual(resp.data["patient"], self.patient.pk)

    def test_doctor_records_event(self):
        doctor = make_user("doc1", UserRole.DOCTOR, self.hospital)
        client = auth_client(doctor)
        resp = client.post(self.url, {
            "patient": self.patient.pk,
            "admission": self.admission.pk,
            "event_type": EventType.DOCTOR_NOTE,
            "payload": {},
            "notes": "Patient improving.",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_ward_staff_cannot_record(self):
        client = auth_client(self.ward_staff)
        resp = client.post(self.url, {
            "patient": self.patient.pk,
            "admission": self.admission.pk,
            "event_type": EventType.VITALS,
            "payload": VITALS,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().post(self.url, {})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_discharged_admission_returns_400(self):
        self.admission.discharged_at = now()
        self.admission.save(update_fields=["discharged_at"])
        client = auth_client(self.nurse)
        resp = client.post(self.url, {
            "patient": self.patient.pk,
            "admission": self.admission.pk,
            "event_type": EventType.VITALS,
            "payload": VITALS,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_patient_returns_400(self):
        other_patient = make_patient(self.hospital, mrn="MRN002")
        client = auth_client(self.nurse)
        resp = client.post(self.url, {
            "patient": other_patient.pk,
            "admission": self.admission.pk,
            "event_type": EventType.VITALS,
            "payload": VITALS,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_event_type_returns_400(self):
        client = auth_client(self.nurse)
        resp = client.post(self.url, {
            "patient": self.patient.pk,
            "admission": self.admission.pk,
            "event_type": "INVALID_TYPE",
            "payload": {},
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------- GET /events/ ----------

class TestEventListView(APITestCase):
    url = "/api/v1/events/"

    def setUp(self):
        self.hospital = make_hospital()
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.nurse)
        record_event(user=self.nurse, patient=self.patient, admission=self.admission,
                     event_type=EventType.VITALS, payload=VITALS)
        record_event(user=self.nurse, patient=self.patient, admission=self.admission,
                     event_type=EventType.MEDICATION, payload={"drug": "paracetamol"})

    def test_lists_hospital_events(self):
        client = auth_client(self.nurse)
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    def test_does_not_return_other_hospital_events(self):
        h2 = make_hospital("H2")
        nurse2 = make_user("nurse2", UserRole.NURSE, h2)
        p2 = make_patient(h2, mrn="MRN-H2")
        a2 = make_admission(p2, nurse2)
        record_event(user=nurse2, patient=p2, admission=a2, event_type=EventType.VITALS, payload={})

        client = auth_client(self.nurse)
        resp = client.get(self.url)
        self.assertEqual(resp.data["count"], 2)

    def test_filter_by_event_type(self):
        client = auth_client(self.nurse)
        resp = client.get(self.url, {"event_type": EventType.VITALS})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["event_type"], EventType.VITALS)

    def test_filter_by_patient(self):
        p2 = make_patient(self.hospital, mrn="MRN002")
        a2 = make_admission(p2, self.nurse)
        record_event(user=self.nurse, patient=p2, admission=a2, event_type=EventType.VITALS, payload={})

        client = auth_client(self.nurse)
        resp = client.get(self.url, {"patient": self.patient.pk})
        self.assertEqual(resp.data["count"], 2)

    def test_filter_by_admission(self):
        p2 = make_patient(self.hospital, mrn="MRN002")
        a2 = make_admission(p2, self.nurse)
        record_event(user=self.nurse, patient=p2, admission=a2, event_type=EventType.VITALS, payload={})

        client = auth_client(self.nurse)
        resp = client.get(self.url, {"admission": self.admission.pk})
        self.assertEqual(resp.data["count"], 2)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------- GET /patients/<id>/events/ ----------

class TestPatientEventTimelineView(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.nurse)
        record_event(user=self.nurse, patient=self.patient, admission=self.admission,
                     event_type=EventType.VITALS, payload=VITALS)
        record_event(user=self.nurse, patient=self.patient, admission=self.admission,
                     event_type=EventType.NURSE_NOTE, payload={}, notes="Resting well.")

    def url(self, pk=None):
        return f"/api/v1/patients/{pk or self.patient.pk}/events/"

    def test_returns_patient_timeline(self):
        client = auth_client(self.nurse)
        resp = client.get(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    def test_filter_by_event_type(self):
        client = auth_client(self.nurse)
        resp = client.get(self.url(), {"event_type": EventType.VITALS})
        self.assertEqual(resp.data["count"], 1)

    def test_other_hospital_patient_returns_404(self):
        h2 = make_hospital("H2")
        nurse2 = make_user("nurse2", UserRole.NURSE, h2)
        p2 = make_patient(h2, mrn="MRN-H2")
        client = auth_client(self.nurse)
        resp = client.get(self.url(p2.pk))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().get(self.url())
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_does_not_bleed_other_patients_events(self):
        p2 = make_patient(self.hospital, mrn="MRN002")
        a2 = make_admission(p2, self.nurse)
        record_event(user=self.nurse, patient=p2, admission=a2, event_type=EventType.VITALS, payload={})

        client = auth_client(self.nurse)
        resp = client.get(self.url())
        self.assertEqual(resp.data["count"], 2)
