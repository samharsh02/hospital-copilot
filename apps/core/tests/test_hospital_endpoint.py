from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.constants import HospitalType
from apps.core.models import Hospital
from apps.users.constants import UserRole

User = get_user_model()


def make_hospital(name="City Hospital"):
    return Hospital.all_objects.create(
        name=name, type=HospitalType.PRIVATE_SINGLE,
        city="Mumbai", state="Maharashtra", bed_count=100,
    )


def make_user(username, role=UserRole.ADMIN, hospital=None):
    return User.objects.create_user(username=username, password="Pass1234!", role=role, hospital=hospital)


def auth_client(user):
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


class TestHospitalDetailView(APITestCase):
    url = "/api/v1/hospital/"

    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user("admin1", hospital=self.hospital)

    def test_returns_hospital_info(self):
        resp = auth_client(self.user).get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["name"], "City Hospital")

    def test_response_includes_clinical_module_flag(self):
        resp = auth_client(self.user).get(self.url)
        self.assertIn("clinical_module_enabled", resp.data)
        self.assertFalse(resp.data["clinical_module_enabled"])

    def test_clinical_module_true_when_enabled(self):
        self.hospital.clinical_module_enabled = True
        self.hospital.save()
        resp = auth_client(self.user).get(self.url)
        self.assertTrue(resp.data["clinical_module_enabled"])

    def test_user_without_hospital_returns_404(self):
        no_hospital_user = make_user("orphan", hospital=None)
        resp = auth_client(no_hospital_user).get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_nurse_can_also_access_hospital_info(self):
        nurse = make_user("nurse1", role=UserRole.NURSE, hospital=self.hospital)
        resp = auth_client(nurse).get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
