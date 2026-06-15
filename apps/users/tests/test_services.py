import pytest
from django.test import TestCase

from apps.core.exceptions import ConflictError
from apps.core.models import Hospital
from apps.core.constants import HospitalType
from apps.users.constants import UserRole
from apps.users.services import register_user


def make_hospital():
    return Hospital.all_objects.create(
        name="City Hospital",
        type=HospitalType.PRIVATE_SINGLE,
        city="Mumbai",
        state="Maharashtra",
        bed_count=100,
    )


class TestRegisterUser(TestCase):
    def test_creates_user_with_required_fields(self):
        user = register_user(username="alice", email="alice@example.com", password="Secret123!")
        self.assertEqual(user.username, "alice")
        self.assertEqual(user.email, "alice@example.com")
        self.assertTrue(user.check_password("Secret123!"))

    def test_defaults_role_to_ward_staff(self):
        user = register_user(username="bob", email="", password="Secret123!")
        self.assertEqual(user.role, UserRole.WARD_STAFF)

    def test_sets_explicit_role(self):
        user = register_user(username="doc", email="", password="Secret123!", role=UserRole.DOCTOR)
        self.assertEqual(user.role, UserRole.DOCTOR)

    def test_sets_hospital(self):
        hospital = make_hospital()
        user = register_user(username="nurse", email="", password="Secret123!", hospital=hospital)
        self.assertEqual(user.hospital_id, hospital.pk)

    def test_sets_phone(self):
        user = register_user(username="charlie", email="", password="Secret123!", phone="9876543210")
        self.assertEqual(user.phone, "9876543210")

    def test_raises_conflict_on_duplicate_username(self):
        register_user(username="dave", email="dave@example.com", password="Secret123!")
        with self.assertRaises(ConflictError) as ctx:
            register_user(username="dave", email="other@example.com", password="Secret123!")
        self.assertIn("Username", ctx.exception.message)

    def test_raises_conflict_on_duplicate_email(self):
        register_user(username="eve", email="eve@example.com", password="Secret123!")
        with self.assertRaises(ConflictError) as ctx:
            register_user(username="eve2", email="eve@example.com", password="Secret123!")
        self.assertIn("Email", ctx.exception.message)

    def test_allows_blank_email_without_conflict(self):
        register_user(username="u1", email="", password="Secret123!")
        user2 = register_user(username="u2", email="", password="Secret123!")
        self.assertEqual(user2.email, "")
