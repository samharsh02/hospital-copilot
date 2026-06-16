from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.utils.timezone import now
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.constants import HospitalType
from apps.core.models import Hospital
from apps.intelligence.constants import PromptType, RequestStatus
from apps.intelligence.models import IntelligenceRequest
from apps.patients.constants import Gender
from apps.patients.models import Admission, Patient
from apps.users.constants import UserRole

User = get_user_model()


def make_hospital(name="City Hospital", clinical=False):
    return Hospital.all_objects.create(
        name=name, type=HospitalType.PRIVATE_SINGLE,
        city="Delhi", state="Delhi", bed_count=50,
        clinical_module_enabled=clinical,
    )


def make_user(username, role=UserRole.ADMIN, hospital=None):
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


def make_request(patient, admission, user, prompt_type=PromptType.PATIENT_SUMMARY,
                 req_status=RequestStatus.PENDING):
    return IntelligenceRequest.objects.create(
        patient=patient, admission=admission, requested_by=user,
        prompt_type=prompt_type, status=req_status,
        created_by=user, updated_by=user,
    )


def auth_client(user):
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


def _mock_anthropic(text="AI summary."):
    msg = MagicMock()
    msg.content = [MagicMock()]
    msg.content[0].text = text
    msg.usage.input_tokens = 100
    msg.usage.output_tokens = 50
    mock_client = MagicMock()
    mock_client.messages.create.return_value = msg
    return mock_client


# ---------------------------------------------------------------------------
# POST /api/v1/intelligence/query/
# ---------------------------------------------------------------------------

class TestQueryCreateView(APITestCase):
    url = "/api/v1/intelligence/query/"

    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)

    def test_admin_creates_query_returns_202(self):
        with patch("apps.intelligence.services.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _mock_anthropic()
            resp = auth_client(self.admin).post(self.url, {
                "patient": self.patient.pk,
                "admission": self.admission.pk,
                "prompt_type": PromptType.PATIENT_SUMMARY,
            }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn("id", resp.data)

    def test_task_runs_eagerly_and_completes(self):
        with patch("apps.intelligence.services.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _mock_anthropic("Detailed summary.")
            resp = auth_client(self.admin).post(self.url, {
                "patient": self.patient.pk,
                "admission": self.admission.pk,
                "prompt_type": PromptType.PATIENT_SUMMARY,
            }, format="json")
        req_id = resp.data["id"]
        req = IntelligenceRequest.objects.get(pk=req_id)
        self.assertEqual(req.status, RequestStatus.COMPLETED)
        self.assertEqual(req.response_text, "Detailed summary.")

    def test_nurse_cannot_create_query(self):
        resp = auth_client(self.nurse).post(self.url, {
            "patient": self.patient.pk,
            "admission": self.admission.pk,
            "prompt_type": PromptType.PATIENT_SUMMARY,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().post(self.url, {
            "patient": self.patient.pk,
            "admission": self.admission.pk,
            "prompt_type": PromptType.PATIENT_SUMMARY,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_prompt_type_returns_400(self):
        resp = auth_client(self.admin).post(self.url, {
            "patient": self.patient.pk,
            "admission": self.admission.pk,
            "prompt_type": "TOTALLY_INVALID",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_clinical_only_type_without_module_returns_400(self):
        resp = auth_client(self.admin).post(self.url, {
            "patient": self.patient.pk,
            "admission": self.admission.pk,
            "prompt_type": PromptType.RISK_FLAG,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_clinical_only_type_with_module_returns_202(self):
        self.hospital.clinical_module_enabled = True
        self.hospital.save()
        with patch("apps.intelligence.services.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _mock_anthropic()
            resp = auth_client(self.admin).post(self.url, {
                "patient": self.patient.pk,
                "admission": self.admission.pk,
                "prompt_type": PromptType.RISK_FLAG,
            }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

    def test_other_hospital_patient_returns_404(self):
        h2 = make_hospital("H2")
        a2 = make_user("a2", UserRole.ADMIN, h2)
        p2 = make_patient(h2, "MRN-H2")
        adm2 = make_admission(p2, a2)
        resp = auth_client(self.admin).post(self.url, {
            "patient": p2.pk,
            "admission": adm2.pk,
            "prompt_type": PromptType.PATIENT_SUMMARY,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_wrong_admission_for_patient_returns_404(self):
        p2 = make_patient(self.hospital, "MRN002")
        adm2 = make_admission(p2, self.admin)
        resp = auth_client(self.admin).post(self.url, {
            "patient": self.patient.pk,
            "admission": adm2.pk,   # belongs to p2, not self.patient
            "prompt_type": PromptType.PATIENT_SUMMARY,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# GET /api/v1/intelligence/<pk>/
# ---------------------------------------------------------------------------

class TestQueryDetailView(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        self.req = make_request(self.patient, self.admission, self.admin)

    def url(self, pk=None):
        return f"/api/v1/intelligence/{pk or self.req.pk}/"

    def test_returns_pending_request(self):
        resp = auth_client(self.admin).get(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], RequestStatus.PENDING)

    def test_returns_completed_request(self):
        self.req.status = RequestStatus.COMPLETED
        self.req.response_text = "Summary here."
        self.req.save()
        resp = auth_client(self.admin).get(self.url())
        self.assertEqual(resp.data["status"], RequestStatus.COMPLETED)
        self.assertEqual(resp.data["response_text"], "Summary here.")

    def test_other_hospital_request_returns_404(self):
        h2 = make_hospital("H2")
        a2 = make_user("a2", UserRole.ADMIN, h2)
        p2 = make_patient(h2, "MRN-H2")
        adm2 = make_admission(p2, a2)
        req2 = make_request(p2, adm2, a2)
        resp = auth_client(self.admin).get(self.url(req2.pk))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().get(self.url())
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# GET /api/v1/patients/<pk>/intelligence/
# ---------------------------------------------------------------------------

class TestPatientIntelligenceHistoryView(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        make_request(self.patient, self.admission, self.admin)
        make_request(self.patient, self.admission, self.admin, PromptType.DISCHARGE_READINESS)

    def url(self, pk=None):
        return f"/api/v1/patients/{pk or self.patient.pk}/intelligence/"

    def test_lists_requests_for_patient(self):
        resp = auth_client(self.admin).get(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    def test_nurse_can_view_history(self):
        resp = auth_client(self.nurse).get(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_other_hospital_patient_returns_404(self):
        h2 = make_hospital("H2")
        a2 = make_user("a2", UserRole.ADMIN, h2)
        p2 = make_patient(h2, "MRN-H2")
        resp = auth_client(self.admin).get(self.url(p2.pk))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().get(self.url())
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_does_not_bleed_other_patients(self):
        p2 = make_patient(self.hospital, "MRN002")
        adm2 = make_admission(p2, self.admin)
        make_request(p2, adm2, self.admin)
        resp = auth_client(self.admin).get(self.url())
        self.assertEqual(resp.data["count"], 2)  # only self.patient's requests
