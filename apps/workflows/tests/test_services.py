from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import now

from apps.core.constants import HospitalType
from apps.core.exceptions import ConflictError
from apps.core.exceptions import ValidationError as AppValidationError
from apps.core.models import Hospital
from apps.patients.constants import Gender
from apps.patients.models import Admission, Patient
from apps.users.constants import UserRole
from apps.workflows.constants import InstanceStatus, WorkflowTrigger
from apps.workflows.models import WorkflowInstance, WorkflowStep, WorkflowTemplate
from apps.workflows.services import (
    cancel_workflow,
    complete_step,
    create_template,
    get_template_queryset,
    start_workflow,
    update_template,
)

User = get_user_model()

STEPS = [
    {"index": 1, "title": "Check vitals"},
    {"index": 2, "title": "Administer meds"},
    {"index": 3, "title": "Document outcome"},
]


def make_hospital(name="General Hospital"):
    return Hospital.all_objects.create(
        name=name, type=HospitalType.PRIVATE_SINGLE,
        city="Delhi", state="Delhi", bed_count=50,
    )


def make_user(username="staff", role=UserRole.ADMIN, hospital=None):
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


def make_template(hospital, user, steps=None, name="Admission Checklist"):
    return WorkflowTemplate.objects.create(
        name=name, hospital=hospital,
        steps=steps or STEPS,
        trigger=WorkflowTrigger.MANUAL,
        created_by=user, updated_by=user,
    )


# ---------- create_template ----------

class TestCreateTemplate(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)

    def test_creates_template(self):
        t = create_template(
            user=self.admin, hospital=self.hospital, name="Test",
            steps=STEPS, trigger=WorkflowTrigger.MANUAL,
        )
        self.assertEqual(t.name, "Test")
        self.assertEqual(t.hospital, self.hospital)
        self.assertEqual(len(t.steps), 3)

    def test_empty_steps_raises(self):
        with self.assertRaises(AppValidationError):
            create_template(
                user=self.admin, hospital=self.hospital, name="Test",
                steps=[], trigger=WorkflowTrigger.MANUAL,
            )

    def test_non_list_steps_raises(self):
        with self.assertRaises(AppValidationError):
            create_template(
                user=self.admin, hospital=self.hospital, name="Test",
                steps={"index": 1, "title": "Bad"}, trigger=WorkflowTrigger.MANUAL,
            )

    def test_step_missing_index_raises(self):
        with self.assertRaises(AppValidationError):
            create_template(
                user=self.admin, hospital=self.hospital, name="Test",
                steps=[{"title": "No index"}], trigger=WorkflowTrigger.MANUAL,
            )

    def test_step_missing_title_raises(self):
        with self.assertRaises(AppValidationError):
            create_template(
                user=self.admin, hospital=self.hospital, name="Test",
                steps=[{"index": 1}], trigger=WorkflowTrigger.MANUAL,
            )


# ---------- get_template_queryset ----------

class TestGetTemplateQueryset(TestCase):
    def setUp(self):
        self.h1 = make_hospital("H1")
        self.h2 = make_hospital("H2")
        self.admin = make_user("admin1", UserRole.ADMIN, self.h1)
        self.superadmin = make_user("sa", UserRole.SUPERADMIN)
        make_template(self.h1, self.admin, name="H1 Template")
        make_template(self.h2, make_user("admin2", UserRole.ADMIN, self.h2), name="H2 Template")

    def test_non_superadmin_sees_own_hospital(self):
        qs = get_template_queryset(user=self.admin)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().hospital, self.h1)

    def test_superadmin_sees_all(self):
        qs = get_template_queryset(user=self.superadmin)
        self.assertEqual(qs.count(), 2)


# ---------- update_template ----------

class TestUpdateTemplate(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.template = make_template(self.hospital, self.admin)

    def test_updates_name(self):
        updated = update_template(user=self.admin, template=self.template, name="New Name")
        self.assertEqual(updated.name, "New Name")

    def test_updates_steps(self):
        new_steps = [{"index": 1, "title": "Only step"}]
        updated = update_template(user=self.admin, template=self.template, steps=new_steps)
        self.assertEqual(len(updated.steps), 1)

    def test_invalid_steps_raises(self):
        with self.assertRaises(AppValidationError):
            update_template(user=self.admin, template=self.template, steps=[])


# ---------- start_workflow ----------

class TestStartWorkflow(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        self.template = make_template(self.hospital, self.admin)

    def test_creates_instance(self):
        instance = start_workflow(user=self.nurse, template=self.template, admission=self.admission)
        self.assertIsInstance(instance, WorkflowInstance)
        self.assertEqual(instance.status, InstanceStatus.PENDING)
        self.assertEqual(instance.template, self.template)

    def test_creates_steps_from_template(self):
        instance = start_workflow(user=self.nurse, template=self.template, admission=self.admission)
        steps = list(instance.steps.order_by("step_index"))
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0].step_index, 1)
        self.assertEqual(steps[0].title, "Check vitals")
        self.assertFalse(steps[0].is_completed)

    def test_template_hospital_mismatch_raises(self):
        other_hospital = make_hospital("Other")
        other_admin = make_user("oadmin", UserRole.ADMIN, other_hospital)
        other_template = make_template(other_hospital, other_admin, name="Other Template")
        with self.assertRaises(AppValidationError):
            start_workflow(user=self.nurse, template=other_template, admission=self.admission)

    def test_discharged_admission_raises(self):
        self.admission.discharged_at = now()
        self.admission.save(update_fields=["discharged_at"])
        with self.assertRaises(AppValidationError):
            start_workflow(user=self.nurse, template=self.template, admission=self.admission)

    def test_inactive_template_raises(self):
        self.template.is_active = False
        self.template.save(update_fields=["is_active"])
        with self.assertRaises(AppValidationError):
            start_workflow(user=self.nurse, template=self.template, admission=self.admission)

    def test_assigned_to_is_set(self):
        instance = start_workflow(
            user=self.nurse, template=self.template,
            admission=self.admission, assigned_to=self.nurse,
        )
        self.assertEqual(instance.assigned_to, self.nurse)


# ---------- complete_step ----------

class TestCompleteStep(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        self.template = make_template(self.hospital, self.admin)
        self.instance = start_workflow(user=self.nurse, template=self.template, admission=self.admission)

    def test_completes_step(self):
        step = complete_step(user=self.nurse, instance=self.instance, step_index=1)
        self.assertTrue(step.is_completed)
        self.assertEqual(step.completed_by, self.nurse)
        self.assertIsNotNone(step.completed_at)

    def test_first_step_sets_in_progress(self):
        complete_step(user=self.nurse, instance=self.instance, step_index=1)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, InstanceStatus.IN_PROGRESS)
        self.assertIsNotNone(self.instance.started_at)

    def test_all_steps_sets_completed(self):
        for idx in [1, 2, 3]:
            complete_step(user=self.nurse, instance=self.instance, step_index=idx)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, InstanceStatus.COMPLETED)
        self.assertIsNotNone(self.instance.completed_at)

    def test_already_completed_step_raises(self):
        complete_step(user=self.nurse, instance=self.instance, step_index=1)
        with self.assertRaises(ConflictError):
            complete_step(user=self.nurse, instance=self.instance, step_index=1)

    def test_invalid_step_index_raises(self):
        with self.assertRaises(AppValidationError):
            complete_step(user=self.nurse, instance=self.instance, step_index=99)

    def test_step_notes_saved(self):
        step = complete_step(user=self.nurse, instance=self.instance, step_index=1, notes="Done carefully.")
        self.assertEqual(step.notes, "Done carefully.")

    def test_completed_instance_raises(self):
        for idx in [1, 2, 3]:
            complete_step(user=self.nurse, instance=self.instance, step_index=idx)
        self.instance.refresh_from_db()
        with self.assertRaises(AppValidationError):
            complete_step(user=self.nurse, instance=self.instance, step_index=1)


# ---------- cancel_workflow ----------

class TestCancelWorkflow(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.admin = make_user("admin1", UserRole.ADMIN, self.hospital)
        self.nurse = make_user("nurse1", UserRole.NURSE, self.hospital)
        self.patient = make_patient(self.hospital)
        self.admission = make_admission(self.patient, self.admin)
        self.template = make_template(self.hospital, self.admin)
        self.instance = start_workflow(user=self.nurse, template=self.template, admission=self.admission)

    def test_cancels_pending_instance(self):
        cancelled = cancel_workflow(user=self.nurse, instance=self.instance)
        self.assertEqual(cancelled.status, InstanceStatus.CANCELLED)

    def test_cancels_in_progress_instance(self):
        complete_step(user=self.nurse, instance=self.instance, step_index=1)
        self.instance.refresh_from_db()
        cancelled = cancel_workflow(user=self.nurse, instance=self.instance)
        self.assertEqual(cancelled.status, InstanceStatus.CANCELLED)

    def test_cancel_completed_raises(self):
        for idx in [1, 2, 3]:
            complete_step(user=self.nurse, instance=self.instance, step_index=idx)
        self.instance.refresh_from_db()
        with self.assertRaises(AppValidationError):
            cancel_workflow(user=self.nurse, instance=self.instance)

    def test_cancel_already_cancelled_raises(self):
        cancel_workflow(user=self.nurse, instance=self.instance)
        self.instance.refresh_from_db()
        with self.assertRaises(AppValidationError):
            cancel_workflow(user=self.nurse, instance=self.instance)
