from django.contrib.auth import get_user_model
from django.utils.timezone import now
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.constants import HospitalType
from apps.core.models import Hospital
from apps.escalations.constants import AlertPriority, AlertStatus
from apps.escalations.models import EscalationAlert, EscalationRule
from apps.patients.constants import Gender
from apps.patients.models import Admission, Patient
from apps.users.constants import UserRole

User = get_user_model()

CONDITION = {"field": "payload.spo2", "op": "lt", "value": 90}


def make_hospital(name="City Hospital"):
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


def make_rule(hospital, user, name="SpO2 Low", is_active=True):
    return EscalationRule.objects.create(
        hospital=hospital, name=name, condition=CONDITION,
        priority=AlertPriority.HIGH, notify_roles=["NURSE"],
        is_active=is_active, created_by=user, updated_by=user,
    )


def make_alert(rule, patient, admission):
    return EscalationAlert.objects.create(
        rule=rule, patient=patient, admission=admission,
    )


def auth_client(user):
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


# ---------- Rule list / create ----------

class TestRuleListCreateView(APITestCase):
    url = "/api/v1/escalation-rules/"

    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        make_rule(self.hospital, self.admin, name="Rule A")
        make_rule(self.hospital, self.admin, name="Rule B")

    def test_admin_lists_rules(self):
        resp = auth_client(self.admin).get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    def test_does_not_return_other_hospital_rules(self):
        h2 = make_hospital("H2")
        a2 = make_user("a2", UserRole.ADMIN, h2)
        make_rule(h2, a2, name="H2 Rule")
        resp = auth_client(self.admin).get(self.url)
        self.assertEqual(resp.data["count"], 2)

    def test_nurse_cannot_list_rules(self):
        resp = auth_client(self.nurse).get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_creates_rule(self):
        resp = auth_client(self.admin).post(self.url, {
            "name": "High Temp",
            "condition": {"field": "payload.temp", "op": "gt", "value": 39},
            "priority": AlertPriority.CRITICAL,
            "notify_roles": ["DOCTOR"],
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["name"], "High Temp")

    def test_nurse_cannot_create_rule(self):
        resp = auth_client(self.nurse).post(self.url, {
            "name": "Bad",
            "condition": CONDITION,
            "priority": AlertPriority.LOW,
            "notify_roles": [],
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_condition_returns_400(self):
        resp = auth_client(self.admin).post(self.url, {
            "name": "Bad",
            "condition": {"op": "lt", "value": 90},
            "priority": AlertPriority.LOW,
            "notify_roles": [],
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------- Rule detail ----------

class TestRuleDetailView(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.rule = make_rule(self.hospital, self.admin)

    def url(self, pk=None):
        return f"/api/v1/escalation-rules/{pk or self.rule.pk}/"

    def test_admin_gets_rule(self):
        resp = auth_client(self.admin).get(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["id"], self.rule.pk)

    def test_nurse_cannot_get_rule(self):
        resp = auth_client(self.nurse).get(self.url())
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_patches_rule(self):
        resp = auth_client(self.admin).patch(self.url(), {"name": "Updated"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["name"], "Updated")

    def test_invalid_condition_patch_returns_400(self):
        resp = auth_client(self.admin).patch(self.url(), {
            "condition": {"field": "payload.x", "op": "UNKNOWN", "value": 1}
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_soft_deletes_rule(self):
        resp = auth_client(self.admin).delete(self.url())
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.rule.refresh_from_db()
        self.assertTrue(self.rule.is_deleted)

    def test_other_hospital_rule_returns_404(self):
        h2 = make_hospital("H2")
        a2 = make_user("a2", UserRole.ADMIN, h2)
        r2 = make_rule(h2, a2, name="H2 Rule")
        resp = auth_client(self.admin).get(self.url(r2.pk))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ---------- Alert list ----------

class TestAlertListView(APITestCase):
    url = "/api/v1/escalation-alerts/"

    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        self.rule = make_rule(self.hospital, self.admin)
        make_alert(self.rule, self.patient, self.admission)
        make_alert(self.rule, self.patient, self.admission)

    def test_nurse_lists_alerts(self):
        resp = auth_client(self.nurse).get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    def test_does_not_return_other_hospital_alerts(self):
        h2 = make_hospital("H2")
        a2 = make_user("a2", UserRole.ADMIN, h2)
        p2 = make_patient(h2, "MRN-H2")
        adm2 = make_admission(p2, a2)
        r2 = make_rule(h2, a2, name="H2 Rule")
        make_alert(r2, p2, adm2)
        resp = auth_client(self.nurse).get(self.url)
        self.assertEqual(resp.data["count"], 2)

    def test_filter_by_status(self):
        # acknowledge one alert
        alert = EscalationAlert.objects.first()
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.save(update_fields=["status"])

        resp = auth_client(self.nurse).get(self.url, {"status": "OPEN"})
        self.assertEqual(resp.data["count"], 1)

    def test_filter_by_patient(self):
        p2 = make_patient(self.hospital, mrn="MRN002")
        adm2 = make_admission(p2, self.admin)
        make_alert(self.rule, p2, adm2)
        resp = auth_client(self.nurse).get(self.url, {"patient": self.patient.pk})
        self.assertEqual(resp.data["count"], 2)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------- Acknowledge ----------

class TestAcknowledgeAlertView(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.ward_staff = make_user("ws1", UserRole.WARD_STAFF, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        self.rule = make_rule(self.hospital, self.admin)
        self.alert = make_alert(self.rule, self.patient, self.admission)

    def url(self, pk=None):
        return f"/api/v1/escalation-alerts/{pk or self.alert.pk}/acknowledge/"

    def test_nurse_acknowledges_alert(self):
        resp = auth_client(self.nurse).post(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], AlertStatus.ACKNOWLEDGED)

    def test_ward_staff_cannot_acknowledge(self):
        resp = auth_client(self.ward_staff).post(self.url())
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_already_acknowledged_returns_400(self):
        auth_client(self.nurse).post(self.url())
        resp = auth_client(self.nurse).post(self.url())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_hospital_alert_returns_404(self):
        h2 = make_hospital("H2")
        a2 = make_user("a2", UserRole.ADMIN, h2)
        p2 = make_patient(h2, "MRN-H2")
        adm2 = make_admission(p2, a2)
        r2 = make_rule(h2, a2, name="H2 Rule")
        alert2 = make_alert(r2, p2, adm2)
        resp = auth_client(self.nurse).post(self.url(alert2.pk))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ---------- Resolve ----------

class TestResolveAlertView(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.doctor = make_user("doc1", UserRole.DOCTOR, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        self.rule = make_rule(self.hospital, self.admin)
        self.alert = make_alert(self.rule, self.patient, self.admission)

    def url(self, pk=None):
        return f"/api/v1/escalation-alerts/{pk or self.alert.pk}/resolve/"

    def test_doctor_resolves_alert(self):
        resp = auth_client(self.doctor).post(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], AlertStatus.RESOLVED)

    def test_admin_resolves_alert(self):
        resp = auth_client(self.admin).post(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_nurse_cannot_resolve(self):
        resp = auth_client(self.nurse).post(self.url())
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_already_resolved_returns_409(self):
        auth_client(self.doctor).post(self.url())
        resp = auth_client(self.doctor).post(self.url())
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_doctor_can_resolve_acknowledged_alert(self):
        self.alert.status = AlertStatus.ACKNOWLEDGED
        self.alert.save(update_fields=["status"])
        resp = auth_client(self.doctor).post(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], AlertStatus.RESOLVED)


# ---------- End-to-end: record_event triggers rule evaluation ----------

class TestEventTriggersEscalation(APITestCase):
    """Verifies the full pipeline: POST /events/ → Celery task (eager) → alert created."""

    def setUp(self):
        self.hospital = make_hospital()
        self.hospital.clinical_module_enabled = True
        self.hospital.save(update_fields=["clinical_module_enabled"])
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        make_rule(self.hospital, self.admin, name="SpO2 Alert")

    def test_low_spo2_event_creates_alert(self):
        resp = auth_client(self.nurse).post("/api/v1/events/", {
            "patient": self.patient.pk,
            "admission": self.admission.pk,
            "event_type": "VITALS",
            "payload": {"spo2": 85},
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(EscalationAlert.objects.count(), 1)
        alert = EscalationAlert.objects.first()
        self.assertEqual(alert.status, AlertStatus.OPEN)
        self.assertEqual(alert.patient, self.patient)

    def test_normal_spo2_event_creates_no_alert(self):
        resp = auth_client(self.nurse).post("/api/v1/events/", {
            "patient": self.patient.pk,
            "admission": self.admission.pk,
            "event_type": "VITALS",
            "payload": {"spo2": 98},
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(EscalationAlert.objects.count(), 0)
