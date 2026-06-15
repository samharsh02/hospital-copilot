from django.contrib.auth import get_user_model
from django.utils.timezone import now
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.constants import HospitalType
from apps.core.models import Hospital
from apps.patients.constants import Gender
from apps.patients.models import Admission, Patient
from apps.users.constants import UserRole
from apps.workflows.constants import InstanceStatus, WorkflowTrigger
from apps.workflows.models import WorkflowTemplate
from apps.workflows.services import start_workflow

User = get_user_model()

STEPS = [
    {"index": 1, "title": "Step One"},
    {"index": 2, "title": "Step Two"},
]


def make_hospital(name="Test Hospital"):
    return Hospital.all_objects.create(
        name=name, type=HospitalType.PRIVATE_SINGLE,
        city="Delhi", state="Delhi", bed_count=50,
    )


def make_user(username, role=UserRole.ADMIN, hospital=None, password="Pass1234!"):
    return User.objects.create_user(username=username, password=password, role=role, hospital=hospital)


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


def make_template(hospital, user, name="Checklist", steps=None, is_active=True):
    return WorkflowTemplate.objects.create(
        name=name, hospital=hospital,
        steps=steps or STEPS,
        trigger=WorkflowTrigger.MANUAL,
        is_active=is_active,
        created_by=user, updated_by=user,
    )


def auth_client(user):
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


# ---------- Template list ----------

class TestTemplateListView(APITestCase):
    url = "/api/v1/workflow-templates/"

    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.client = auth_client(self.nurse)
        make_template(self.hospital, self.admin, name="T1")
        make_template(self.hospital, self.admin, name="T2")

    def test_lists_templates_authenticated(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    def test_does_not_return_other_hospital_templates(self):
        h2 = make_hospital("H2")
        admin2 = make_user("admin2", UserRole.ADMIN, h2)
        make_template(h2, admin2, name="H2 Template")
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 2)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------- Template create ----------

class TestTemplateCreateView(APITestCase):
    url = "/api/v1/workflow-templates/"

    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)

    def test_admin_creates_template(self):
        client = auth_client(self.admin)
        resp = client.post(self.url, {
            "name": "Discharge Checklist",
            "steps": STEPS,
            "trigger": WorkflowTrigger.ON_DISCHARGE,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["name"], "Discharge Checklist")
        self.assertEqual(len(resp.data["steps"]), 2)

    def test_nurse_cannot_create_template(self):
        client = auth_client(self.nurse)
        resp = client.post(self.url, {
            "name": "Test", "steps": STEPS, "trigger": WorkflowTrigger.MANUAL,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_empty_steps_returns_400(self):
        client = auth_client(self.admin)
        resp = client.post(self.url, {
            "name": "Bad", "steps": [], "trigger": WorkflowTrigger.MANUAL,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------- Template detail ----------

class TestTemplateDetailView(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.template = make_template(self.hospital, self.admin)

    def url(self, pk=None):
        return f"/api/v1/workflow-templates/{pk or self.template.pk}/"

    def test_get_template(self):
        client = auth_client(self.nurse)
        resp = client.get(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["id"], self.template.pk)

    def test_patch_updates_name(self):
        client = auth_client(self.admin)
        resp = client.patch(self.url(), {"name": "Updated"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["name"], "Updated")

    def test_nurse_cannot_patch(self):
        client = auth_client(self.nurse)
        resp = client.patch(self.url(), {"name": "Updated"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_soft_deletes(self):
        client = auth_client(self.admin)
        resp = client.delete(self.url())
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.template.refresh_from_db()
        self.assertTrue(self.template.is_deleted)

    def test_nurse_cannot_delete(self):
        client = auth_client(self.nurse)
        resp = client.delete(self.url())
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_hospital_template_returns_404(self):
        h2 = make_hospital("H2")
        admin2 = make_user("admin2", UserRole.ADMIN, h2)
        t2 = make_template(h2, admin2, name="H2 T")
        client = auth_client(self.admin)
        resp = client.get(self.url(t2.pk))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ---------- Instance start ----------

class TestStartWorkflowView(APITestCase):
    url = "/api/v1/workflow-instances/"

    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.ward_staff = make_user("ws1", UserRole.WARD_STAFF, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        self.template = make_template(self.hospital, self.admin)

    def test_nurse_starts_workflow(self):
        client = auth_client(self.nurse)
        resp = client.post(self.url, {
            "template": self.template.pk,
            "admission": self.admission.pk,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], InstanceStatus.PENDING)
        self.assertEqual(len(resp.data["steps"]), 2)

    def test_ward_staff_cannot_start(self):
        client = auth_client(self.ward_staff)
        resp = client.post(self.url, {
            "template": self.template.pk,
            "admission": self.admission.pk,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_discharged_admission_returns_400(self):
        self.admission.discharged_at = now()
        self.admission.save(update_fields=["discharged_at"])
        client = auth_client(self.nurse)
        resp = client.post(self.url, {
            "template": self.template.pk,
            "admission": self.admission.pk,
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().post(self.url, {})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------- Instance list ----------

class TestInstanceListView(APITestCase):
    url = "/api/v1/workflow-instances/"

    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        self.template = make_template(self.hospital, self.admin)
        start_workflow(user=self.nurse, template=self.template, admission=self.admission)

    def test_lists_instances(self):
        client = auth_client(self.nurse)
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

    def test_does_not_return_other_hospital_instances(self):
        h2 = make_hospital("H2")
        admin2 = make_user("admin2", UserRole.ADMIN, h2)
        patient2 = make_patient(h2, "MRN-H2")
        admission2 = make_admission(patient2, admin2)
        t2 = make_template(h2, admin2, name="H2T")
        start_workflow(user=admin2, template=t2, admission=admission2)
        client = auth_client(self.nurse)
        resp = client.get(self.url)
        self.assertEqual(resp.data["count"], 1)


# ---------- Instance detail ----------

class TestInstanceDetailView(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        self.template = make_template(self.hospital, self.admin)
        self.instance = start_workflow(user=self.nurse, template=self.template, admission=self.admission)

    def url(self, pk=None):
        return f"/api/v1/workflow-instances/{pk or self.instance.pk}/"

    def test_get_instance_with_steps(self):
        client = auth_client(self.nurse)
        resp = client.get(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["id"], self.instance.pk)
        self.assertEqual(len(resp.data["steps"]), 2)

    def test_other_hospital_instance_returns_404(self):
        h2 = make_hospital("H2")
        admin2 = make_user("admin2", UserRole.ADMIN, h2)
        patient2 = make_patient(h2, "MRN-H2")
        admission2 = make_admission(patient2, admin2)
        t2 = make_template(h2, admin2, name="H2T")
        inst2 = start_workflow(user=admin2, template=t2, admission=admission2)
        client = auth_client(self.nurse)
        resp = client.get(self.url(inst2.pk))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ---------- Complete step ----------

class TestCompleteStepView(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.ward_staff = make_user("ws1", UserRole.WARD_STAFF, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        self.template = make_template(self.hospital, self.admin)
        self.instance = start_workflow(user=self.nurse, template=self.template, admission=self.admission)

    def url(self, step_index):
        return f"/api/v1/workflow-instances/{self.instance.pk}/steps/{step_index}/complete/"

    def test_nurse_completes_step(self):
        client = auth_client(self.nurse)
        resp = client.post(self.url(1), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["is_completed"])

    def test_ward_staff_cannot_complete(self):
        client = auth_client(self.ward_staff)
        resp = client.post(self.url(1), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_already_completed_returns_409(self):
        client = auth_client(self.nurse)
        client.post(self.url(1), {}, format="json")
        resp = client.post(self.url(1), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_invalid_step_returns_400(self):
        client = auth_client(self.nurse)
        resp = client.post(self.url(99), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_notes_saved(self):
        client = auth_client(self.nurse)
        resp = client.post(self.url(1), {"notes": "All good."}, format="json")
        self.assertEqual(resp.data["notes"], "All good.")


# ---------- Cancel workflow ----------

class TestCancelWorkflowView(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.ward_staff = make_user("ws1", UserRole.WARD_STAFF, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        self.template = make_template(self.hospital, self.admin)
        self.instance = start_workflow(user=self.nurse, template=self.template, admission=self.admission)

    def url(self, pk=None):
        return f"/api/v1/workflow-instances/{pk or self.instance.pk}/cancel/"

    def test_nurse_cancels_instance(self):
        client = auth_client(self.nurse)
        resp = client.post(self.url(), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], InstanceStatus.CANCELLED)

    def test_ward_staff_cannot_cancel(self):
        client = auth_client(self.ward_staff)
        resp = client.post(self.url(), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
