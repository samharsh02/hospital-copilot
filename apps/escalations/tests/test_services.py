from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from apps.core.constants import HospitalType
from apps.core.exceptions import ConflictError
from apps.core.exceptions import ValidationError as AppValidationError
from apps.core.models import Hospital
from apps.escalations.constants import AlertPriority, AlertStatus
from apps.escalations.models import EscalationAlert, EscalationRule
from apps.escalations.services import (
    _evaluate_condition,
    acknowledge_alert,
    create_rule,
    evaluate_escalation_rules,
    get_alert_queryset,
    get_rule_queryset,
    resolve_alert,
    update_rule,
)
from apps.events.constants import EventType
from apps.events.models import ClinicalEvent
from apps.patients.constants import Gender
from apps.patients.models import Admission, Patient
from apps.users.constants import UserRole

User = get_user_model()

CONDITION_SPO2_LOW = {"field": "payload.spo2", "op": "lt", "value": 90}
CONDITION_VITALS_TYPE = {"field": "event_type", "op": "eq", "value": "VITALS"}


def make_hospital(name="General Hospital"):
    return Hospital.all_objects.create(
        name=name, type=HospitalType.PRIVATE_SINGLE,
        city="Delhi", state="Delhi", bed_count=50,
    )


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


def make_event(patient, admission, user, event_type=EventType.VITALS, payload=None):
    return ClinicalEvent.objects.create(
        patient=patient, admission=admission, event_type=event_type,
        recorded_by=user, payload=payload or {"spo2": 95},
        created_by=user, updated_by=user,
    )


def make_rule(hospital, user, condition=None, name="Low SpO2", priority=AlertPriority.HIGH):
    return EscalationRule.objects.create(
        hospital=hospital, name=name,
        condition=condition or CONDITION_SPO2_LOW,
        priority=priority,
        notify_roles=["NURSE", "DOCTOR"],
        created_by=user, updated_by=user,
    )


# ---------- condition DSL ----------

class TestEvaluateCondition(TestCase):
    def _make_event(self, payload, event_type=EventType.VITALS):
        h = make_hospital()
        u = make_user(hospital=h)
        p = make_patient(h)
        a = make_admission(p, u)
        return ClinicalEvent(
            patient=p, admission=a, event_type=event_type,
            payload=payload, recorded_by=u,
        )

    def test_lt_match(self):
        e = self._make_event({"spo2": 85})
        self.assertTrue(_evaluate_condition({"field": "payload.spo2", "op": "lt", "value": 90}, e))

    def test_lt_no_match(self):
        e = self._make_event({"spo2": 95})
        self.assertFalse(_evaluate_condition({"field": "payload.spo2", "op": "lt", "value": 90}, e))

    def test_lte_boundary(self):
        e = self._make_event({"spo2": 90})
        self.assertTrue(_evaluate_condition({"field": "payload.spo2", "op": "lte", "value": 90}, e))

    def test_gt_match(self):
        e = self._make_event({"temp": 39.5})
        self.assertTrue(_evaluate_condition({"field": "payload.temp", "op": "gt", "value": 38.5}, e))

    def test_eq_string(self):
        e = self._make_event({}, event_type=EventType.VITALS)
        self.assertTrue(_evaluate_condition({"field": "event_type", "op": "eq", "value": "VITALS"}, e))

    def test_ne_string(self):
        e = self._make_event({}, event_type=EventType.VITALS)
        self.assertTrue(_evaluate_condition({"field": "event_type", "op": "ne", "value": "MEDICATION"}, e))

    def test_in_operator(self):
        e = self._make_event({}, event_type=EventType.VITALS)
        self.assertTrue(_evaluate_condition({"field": "event_type", "op": "in", "value": ["VITALS", "MEDICATION"]}, e))

    def test_missing_payload_field_returns_false(self):
        e = self._make_event({})
        self.assertFalse(_evaluate_condition(CONDITION_SPO2_LOW, e))

    def test_non_numeric_value_returns_false(self):
        e = self._make_event({"spo2": "not-a-number"})
        self.assertFalse(_evaluate_condition(CONDITION_SPO2_LOW, e))

    def test_nested_payload_path(self):
        e = self._make_event({"vitals": {"spo2": 85}})
        cond = {"field": "payload.vitals.spo2", "op": "lt", "value": 90}
        self.assertTrue(_evaluate_condition(cond, e))


# ---------- create_rule ----------

class TestCreateRule(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user(hospital=self.hospital)

    def test_creates_rule(self):
        rule = create_rule(
            user=self.admin, hospital=self.hospital, name="Low SpO2",
            condition=CONDITION_SPO2_LOW, priority=AlertPriority.CRITICAL,
            notify_roles=["NURSE"],
        )
        self.assertEqual(rule.name, "Low SpO2")
        self.assertEqual(rule.hospital, self.hospital)
        self.assertEqual(rule.priority, AlertPriority.CRITICAL)

    def test_invalid_condition_missing_field_raises(self):
        with self.assertRaises(AppValidationError):
            create_rule(user=self.admin, hospital=self.hospital, name="Bad",
                        condition={"op": "lt", "value": 90},
                        priority=AlertPriority.HIGH, notify_roles=[])

    def test_invalid_op_raises(self):
        with self.assertRaises(AppValidationError):
            create_rule(user=self.admin, hospital=self.hospital, name="Bad",
                        condition={"field": "payload.x", "op": "BETWEEN", "value": 5},
                        priority=AlertPriority.HIGH, notify_roles=[])

    def test_in_op_non_list_raises(self):
        with self.assertRaises(AppValidationError):
            create_rule(user=self.admin, hospital=self.hospital, name="Bad",
                        condition={"field": "event_type", "op": "in", "value": "VITALS"},
                        priority=AlertPriority.HIGH, notify_roles=[])


# ---------- get_rule_queryset ----------

class TestGetRuleQueryset(TestCase):
    def setUp(self):
        self.h1 = make_hospital("H1")
        self.h2 = make_hospital("H2")
        self.admin1 = make_user("a1", UserRole.ADMIN, self.h1)
        self.admin2 = make_user("a2", UserRole.ADMIN, self.h2)
        self.superadmin = make_user("sa", UserRole.SUPERADMIN)
        make_rule(self.h1, self.admin1, name="H1 Rule")
        make_rule(self.h2, self.admin2, name="H2 Rule")

    def test_admin_sees_own_hospital(self):
        self.assertEqual(get_rule_queryset(user=self.admin1).count(), 1)

    def test_superadmin_sees_all(self):
        self.assertEqual(get_rule_queryset(user=self.superadmin).count(), 2)


# ---------- evaluate_escalation_rules ----------

class TestEvaluateEscalationRules(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user(hospital=self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)

    def test_matching_rule_creates_alert(self):
        make_rule(self.hospital, self.admin, condition=CONDITION_SPO2_LOW)
        make_event(self.patient, self.admission, self.nurse, payload={"spo2": 85})
        alerts = evaluate_escalation_rules(self.admission.pk)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].status, AlertStatus.OPEN)
        self.assertEqual(alerts[0].patient, self.patient)

    def test_non_matching_rule_creates_no_alert(self):
        make_rule(self.hospital, self.admin, condition=CONDITION_SPO2_LOW)
        make_event(self.patient, self.admission, self.nurse, payload={"spo2": 98})
        alerts = evaluate_escalation_rules(self.admission.pk)
        self.assertEqual(len(alerts), 0)

    def test_inactive_rule_skipped(self):
        rule = make_rule(self.hospital, self.admin, condition=CONDITION_SPO2_LOW)
        rule.is_active = False
        rule.save(update_fields=["is_active"])
        make_event(self.patient, self.admission, self.nurse, payload={"spo2": 85})
        alerts = evaluate_escalation_rules(self.admission.pk)
        self.assertEqual(len(alerts), 0)

    def test_other_hospital_rule_not_evaluated(self):
        h2 = make_hospital("H2")
        admin2 = make_user("a2", UserRole.ADMIN, h2)
        make_rule(h2, admin2, condition=CONDITION_SPO2_LOW, name="H2 Rule")
        make_event(self.patient, self.admission, self.nurse, payload={"spo2": 85})
        alerts = evaluate_escalation_rules(self.admission.pk)
        self.assertEqual(len(alerts), 0)

    def test_dedup_no_duplicate_open_alert(self):
        make_rule(self.hospital, self.admin, condition=CONDITION_SPO2_LOW)
        make_event(self.patient, self.admission, self.nurse, payload={"spo2": 85})
        evaluate_escalation_rules(self.admission.pk)
        # Second event still matches — but existing OPEN alert blocks a new one
        make_event(self.patient, self.admission, self.nurse, payload={"spo2": 83})
        alerts = evaluate_escalation_rules(self.admission.pk)
        self.assertEqual(len(alerts), 0)
        self.assertEqual(EscalationAlert.objects.count(), 1)

    def test_new_alert_after_existing_resolved(self):
        rule = make_rule(self.hospital, self.admin, condition=CONDITION_SPO2_LOW)
        make_event(self.patient, self.admission, self.nurse, payload={"spo2": 85})
        first_alerts = evaluate_escalation_rules(self.admission.pk)
        # Resolve the alert
        resolve_alert(user=self.admin, alert=first_alerts[0])
        # Same condition again — new alert should be created now
        make_event(self.patient, self.admission, self.nurse, payload={"spo2": 82})
        second_alerts = evaluate_escalation_rules(self.admission.pk)
        self.assertEqual(len(second_alerts), 1)

    def test_multiple_rules_multiple_alerts(self):
        make_rule(self.hospital, self.admin, condition=CONDITION_SPO2_LOW, name="SpO2")
        make_rule(self.hospital, self.admin,
                  condition={"field": "event_type", "op": "eq", "value": "VITALS"},
                  name="Any Vitals", priority=AlertPriority.LOW)
        make_event(self.patient, self.admission, self.nurse,
                   event_type=EventType.VITALS, payload={"spo2": 85})
        alerts = evaluate_escalation_rules(self.admission.pk)
        self.assertEqual(len(alerts), 2)

    def test_invalid_admission_id_returns_empty(self):
        alerts = evaluate_escalation_rules(999999)
        self.assertEqual(alerts, [])

    def test_no_events_returns_empty(self):
        make_rule(self.hospital, self.admin, condition=CONDITION_SPO2_LOW)
        alerts = evaluate_escalation_rules(self.admission.pk)
        self.assertEqual(alerts, [])


# ---------- acknowledge_alert ----------

class TestAcknowledgeAlert(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user(hospital=self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        rule = make_rule(self.hospital, self.admin)
        self.alert = EscalationAlert.objects.create(
            rule=rule, patient=self.patient, admission=self.admission,
        )

    def test_acknowledges_open_alert(self):
        alert = acknowledge_alert(user=self.nurse, alert=self.alert)
        self.assertEqual(alert.status, AlertStatus.ACKNOWLEDGED)
        self.assertEqual(alert.acknowledged_by, self.nurse)
        self.assertIsNotNone(alert.acknowledged_at)

    def test_already_acknowledged_raises(self):
        acknowledge_alert(user=self.nurse, alert=self.alert)
        self.alert.refresh_from_db()
        with self.assertRaises(AppValidationError):
            acknowledge_alert(user=self.nurse, alert=self.alert)

    def test_resolved_alert_raises(self):
        resolve_alert(user=self.admin, alert=self.alert)
        self.alert.refresh_from_db()
        with self.assertRaises(AppValidationError):
            acknowledge_alert(user=self.nurse, alert=self.alert)


# ---------- resolve_alert ----------

class TestResolveAlert(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user(hospital=self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        rule = make_rule(self.hospital, self.admin)
        self.alert = EscalationAlert.objects.create(
            rule=rule, patient=self.patient, admission=self.admission,
        )

    def test_resolves_open_alert(self):
        alert = resolve_alert(user=self.admin, alert=self.alert)
        self.assertEqual(alert.status, AlertStatus.RESOLVED)
        self.assertIsNotNone(alert.resolved_at)

    def test_resolves_acknowledged_alert(self):
        acknowledge_alert(user=self.nurse, alert=self.alert)
        self.alert.refresh_from_db()
        alert = resolve_alert(user=self.admin, alert=self.alert)
        self.assertEqual(alert.status, AlertStatus.RESOLVED)

    def test_already_resolved_raises(self):
        resolve_alert(user=self.admin, alert=self.alert)
        self.alert.refresh_from_db()
        with self.assertRaises(ConflictError):
            resolve_alert(user=self.admin, alert=self.alert)
