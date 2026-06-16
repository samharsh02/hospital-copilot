from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from apps.core.constants import HospitalType
from apps.core.exceptions import ValidationError as AppValidationError
from apps.core.models import Hospital
from apps.escalations.constants import AlertPriority
from apps.escalations.models import EscalationAlert, EscalationRule
from apps.events.constants import EventType
from apps.events.models import ClinicalEvent
from apps.intelligence.constants import (
    DISCLAIMER,
    PromptType,
    RequestStatus,
)
from apps.intelligence.models import IntelligenceRequest
from apps.intelligence.services import (
    _build_tier1_context,
    _build_tier2_context,
    build_prompt,
    get_request_queryset,
    mark_request_failed,
    request_ai_query,
    run_ai_query,
)
from apps.patients.constants import Gender
from apps.patients.models import Admission, Patient
from apps.users.constants import UserRole

User = get_user_model()


def make_hospital(name="City Hospital", clinical=False):
    h = Hospital.all_objects.create(
        name=name, type=HospitalType.PRIVATE_SINGLE,
        city="Delhi", state="Delhi", bed_count=50,
        clinical_module_enabled=clinical,
    )
    return h


def make_user(username="admin1", role=UserRole.ADMIN, hospital=None):
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


def _make_mock_anthropic(text="AI summary.", input_tokens=100, output_tokens=50):
    msg = MagicMock()
    msg.content = [MagicMock()]
    msg.content[0].text = text
    msg.usage.input_tokens = input_tokens
    msg.usage.output_tokens = output_tokens
    mock_client = MagicMock()
    mock_client.messages.create.return_value = msg
    return mock_client


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------

class TestBuildTier1Context(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user(hospital=self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.user)

    def test_includes_mrn_and_gender(self):
        ctx = _build_tier1_context(self.admission)
        self.assertIn("MRN001", ctx)
        self.assertIn("FEMALE", ctx)

    def test_includes_los(self):
        ctx = _build_tier1_context(self.admission)
        self.assertIn("Day 1 of admission", ctx)

    def test_no_bed_shows_placeholder(self):
        ctx = _build_tier1_context(self.admission)
        self.assertIn("No bed assigned", ctx)

    def test_discharge_shown_when_present(self):
        self.admission.discharged_at = now()
        self.admission.save()
        ctx = _build_tier1_context(self.admission)
        self.assertIn("DISCHARGE:", ctx)


class TestBuildTier2Context(TestCase):
    def setUp(self):
        self.hospital = make_hospital(clinical=True)
        self.user = make_user(hospital=self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.user)

    def test_no_events_shows_message(self):
        ctx = _build_tier2_context(self.admission)
        self.assertIn("No clinical events recorded", ctx)

    def test_events_shown(self):
        ClinicalEvent.objects.create(
            patient=self.patient, admission=self.admission,
            event_type=EventType.VITALS, payload={"spo2": 95},
            recorded_by=self.user, created_by=self.user, updated_by=self.user,
        )
        ctx = _build_tier2_context(self.admission)
        self.assertIn("VITALS", ctx)
        self.assertIn("spo2=95", ctx)

    def test_open_alerts_shown(self):
        rule = EscalationRule.objects.create(
            hospital=self.hospital, name="SpO2 Low",
            condition={"field": "payload.spo2", "op": "lt", "value": 90},
            priority=AlertPriority.HIGH, notify_roles=[],
            created_by=self.user, updated_by=self.user,
        )
        EscalationAlert.objects.create(rule=rule, patient=self.patient, admission=self.admission)
        ctx = _build_tier2_context(self.admission)
        self.assertIn("SpO2 Low", ctx)
        self.assertIn("HIGH", ctx)

    def test_no_open_alerts_shows_none(self):
        ctx = _build_tier2_context(self.admission)
        self.assertIn("OPEN ESCALATION ALERTS: None.", ctx)


class TestBuildPrompt(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user(hospital=self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.user)

    def _make_req(self, prompt_type=PromptType.PATIENT_SUMMARY):
        return IntelligenceRequest(
            patient=self.patient, admission=self.admission,
            requested_by=self.user, prompt_type=prompt_type,
        )

    def test_clinical_context_false_when_module_off(self):
        req = self._make_req()
        _, clinical_used = build_prompt(req)
        self.assertFalse(clinical_used)

    def test_clinical_context_true_when_module_on(self):
        self.hospital.clinical_module_enabled = True
        self.hospital.save()
        req = self._make_req()
        _, clinical_used = build_prompt(req)
        self.assertTrue(clinical_used)

    def test_module_off_shows_unavailable_message(self):
        req = self._make_req()
        prompt, _ = build_prompt(req)
        self.assertIn("Clinical module not enabled", prompt)

    def test_module_on_shows_clinical_section(self):
        self.hospital.clinical_module_enabled = True
        self.hospital.save()
        req = self._make_req()
        prompt, _ = build_prompt(req)
        self.assertIn("CLINICAL DATA", prompt)
        self.assertNotIn("Clinical module not enabled", prompt)

    def test_task_section_included(self):
        req = self._make_req()
        prompt, _ = build_prompt(req)
        self.assertIn("TASK", prompt)
        self.assertIn("Do NOT diagnose", prompt)

    def test_discharge_readiness_instruction(self):
        req = self._make_req(PromptType.DISCHARGE_READINESS)
        prompt, _ = build_prompt(req)
        self.assertIn("discharge", prompt.lower())


# ---------------------------------------------------------------------------
# request_ai_query
# ---------------------------------------------------------------------------

class TestRequestAiQuery(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user(hospital=self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.user)

    def test_creates_pending_request(self):
        with patch("apps.intelligence.services.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _make_mock_anthropic()
            req = request_ai_query(
                user=self.user, patient=self.patient,
                admission=self.admission, prompt_type=PromptType.PATIENT_SUMMARY,
            )
        self.assertIsNotNone(req.pk)
        # After eager task execution the status is COMPLETED
        req.refresh_from_db()
        self.assertEqual(req.status, RequestStatus.COMPLETED)

    def test_clinical_only_type_blocked_when_module_off(self):
        with self.assertRaises(AppValidationError):
            request_ai_query(
                user=self.user, patient=self.patient,
                admission=self.admission, prompt_type=PromptType.RISK_FLAG,
            )

    def test_clinical_only_type_allowed_when_module_on(self):
        self.hospital.clinical_module_enabled = True
        self.hospital.save()
        with patch("apps.intelligence.services.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _make_mock_anthropic()
            req = request_ai_query(
                user=self.user, patient=self.patient,
                admission=self.admission, prompt_type=PromptType.RISK_FLAG,
            )
        req.refresh_from_db()
        self.assertEqual(req.status, RequestStatus.COMPLETED)


# ---------------------------------------------------------------------------
# run_ai_query
# ---------------------------------------------------------------------------

class TestRunAiQuery(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user(hospital=self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.user)
        self.req = IntelligenceRequest.objects.create(
            patient=self.patient, admission=self.admission,
            requested_by=self.user, prompt_type=PromptType.PATIENT_SUMMARY,
            created_by=self.user, updated_by=self.user,
        )

    def test_success_sets_completed(self):
        mock_client = _make_mock_anthropic("Great summary.")
        with patch("apps.intelligence.services.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = mock_client
            run_ai_query(self.req.pk)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, RequestStatus.COMPLETED)
        self.assertEqual(self.req.response_text, "Great summary.")

    def test_success_sets_tokens_and_latency(self):
        mock_client = _make_mock_anthropic(input_tokens=200, output_tokens=80)
        with patch("apps.intelligence.services.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = mock_client
            run_ai_query(self.req.pk)
        self.req.refresh_from_db()
        self.assertEqual(self.req.tokens_used, 280)
        self.assertIsNotNone(self.req.latency_ms)

    def test_disclaimer_written_on_completion(self):
        with patch("apps.intelligence.services.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _make_mock_anthropic()
            run_ai_query(self.req.pk)
        self.req.refresh_from_db()
        self.assertEqual(self.req.disclaimer, DISCLAIMER)

    def test_clinical_context_used_false_when_module_off(self):
        with patch("apps.intelligence.services.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _make_mock_anthropic()
            run_ai_query(self.req.pk)
        self.req.refresh_from_db()
        self.assertFalse(self.req.clinical_context_used)

    def test_clinical_context_used_true_when_module_on(self):
        self.hospital.clinical_module_enabled = True
        self.hospital.save()
        with patch("apps.intelligence.services.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value = _make_mock_anthropic()
            run_ai_query(self.req.pk)
        self.req.refresh_from_db()
        self.assertTrue(self.req.clinical_context_used)

    def test_api_failure_raises(self):
        with patch("apps.intelligence.services.anthropic") as mock_ant:
            mock_ant.Anthropic.return_value.messages.create.side_effect = RuntimeError("API error")
            with self.assertRaises(RuntimeError):
                run_ai_query(self.req.pk)
        # Status should still be PENDING — the task handles FAILED marking.
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, RequestStatus.PENDING)

    def test_noop_when_already_completed(self):
        self.req.status = RequestStatus.COMPLETED
        self.req.save()
        with patch("apps.intelligence.services.anthropic") as mock_ant:
            run_ai_query(self.req.pk)
            mock_ant.Anthropic.assert_not_called()

    def test_noop_when_nonexistent_id(self):
        run_ai_query(999999)  # should not raise


# ---------------------------------------------------------------------------
# mark_request_failed
# ---------------------------------------------------------------------------

class TestMarkRequestFailed(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user(hospital=self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.user)

    def test_sets_failed_status(self):
        req = IntelligenceRequest.objects.create(
            patient=self.patient, admission=self.admission,
            requested_by=self.user, prompt_type=PromptType.PATIENT_SUMMARY,
            created_by=self.user, updated_by=self.user,
        )
        mark_request_failed(req.pk)
        req.refresh_from_db()
        self.assertEqual(req.status, RequestStatus.FAILED)
        self.assertIsNotNone(req.completed_at)


# ---------------------------------------------------------------------------
# get_request_queryset
# ---------------------------------------------------------------------------

class TestGetRequestQueryset(TestCase):
    def setUp(self):
        self.h1 = make_hospital("H1")
        self.h2 = make_hospital("H2")
        self.admin1 = make_user("a1", UserRole.ADMIN, self.h1)
        self.admin2 = make_user("a2", UserRole.ADMIN, self.h2)
        self.superadmin = make_user("sa", UserRole.SUPERADMIN)
        p1 = make_patient(self.h1, "MRN-H1")
        p2 = make_patient(self.h2, "MRN-H2")
        adm1 = make_admission(p1, self.admin1)
        adm2 = make_admission(p2, self.admin2)
        for req_user, pat, adm in [(self.admin1, p1, adm1), (self.admin2, p2, adm2)]:
            IntelligenceRequest.objects.create(
                patient=pat, admission=adm, requested_by=req_user,
                prompt_type=PromptType.PATIENT_SUMMARY,
                created_by=req_user, updated_by=req_user,
            )

    def test_admin_sees_own_hospital_only(self):
        self.assertEqual(get_request_queryset(user=self.admin1).count(), 1)

    def test_superadmin_sees_all(self):
        self.assertEqual(get_request_queryset(user=self.superadmin).count(), 2)
