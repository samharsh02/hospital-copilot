from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.constants import HospitalType
from apps.core.models import Hospital

User = get_user_model()


def make_user(username="testuser", password="Secret123!", **kwargs):
    return User.objects.create_user(username=username, password=password, **kwargs)


def make_hospital():
    return Hospital.all_objects.create(
        name="City Hospital",
        type=HospitalType.PRIVATE_SINGLE,
        city="Mumbai",
        state="Maharashtra",
        bed_count=100,
    )


class TestRegisterView(APITestCase):
    url = "/api/v1/auth/register/"

    def test_success_returns_201_with_tokens(self):
        resp = self.client.post(self.url, {"username": "alice", "password": "Secret123!"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertIn("user", resp.data)
        self.assertEqual(resp.data["user"]["username"], "alice")

    def test_success_creates_user_in_db(self):
        self.client.post(self.url, {"username": "bob", "password": "Secret123!"}, format="json")
        self.assertTrue(User.objects.filter(username="bob").exists())

    def test_duplicate_username_returns_409(self):
        make_user(username="charlie")
        resp = self.client.post(self.url, {"username": "charlie", "password": "Secret123!"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_weak_password_returns_400(self):
        resp = self.client.post(self.url, {"username": "dave", "password": "123"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_username_returns_400(self):
        resp = self.client.post(self.url, {"password": "Secret123!"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_with_hospital_fk(self):
        hospital = make_hospital()
        resp = self.client.post(
            self.url,
            {"username": "nurse1", "password": "Secret123!", "hospital": hospital.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["user"]["hospital"], hospital.pk)

    def test_does_not_require_auth(self):
        resp = self.client.post(self.url, {"username": "anon", "password": "Secret123!"}, format="json")
        self.assertNotEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class TestLoginView(APITestCase):
    url = "/api/v1/auth/login/"

    def setUp(self):
        self.user = make_user(username="loginuser", password="Secret123!")

    def test_valid_credentials_returns_tokens(self):
        resp = self.client.post(self.url, {"username": "loginuser", "password": "Secret123!"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_wrong_password_returns_400(self):
        resp = self.client.post(self.url, {"username": "loginuser", "password": "WrongPass!"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_user_returns_400(self):
        resp = self.client.post(self.url, {"username": "nobody", "password": "Secret123!"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_fields_returns_400(self):
        resp = self.client.post(self.url, {"username": "loginuser"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_user_returns_400(self):
        self.user.is_active = False
        self.user.save()
        resp = self.client.post(self.url, {"username": "loginuser", "password": "Secret123!"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class TestLogoutView(APITestCase):
    url = "/api/v1/auth/logout/"

    def setUp(self):
        self.user = make_user(username="logoutuser", password="Secret123!")
        self.refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.refresh.access_token}")

    def test_valid_refresh_token_returns_204(self):
        resp = self.client.post(self.url, {"refresh": str(self.refresh)}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_missing_refresh_token_returns_400(self):
        resp = self.client.post(self.url, {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_refresh_token_returns_400(self):
        resp = self.client.post(self.url, {"refresh": "not-a-real-token"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.post(self.url, {"refresh": str(self.refresh)}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class TestMeView(APITestCase):
    url = "/api/v1/auth/me/"

    def setUp(self):
        self.user = make_user(username="meuser", password="Secret123!", email="me@example.com")
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def test_get_returns_user_data(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["username"], "meuser")
        self.assertEqual(resp.data["email"], "me@example.com")

    def test_get_unauthenticated_returns_401(self):
        client = APIClient()
        resp = client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patch_updates_first_name(self):
        resp = self.client.patch(self.url, {"first_name": "Alice"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["first_name"], "Alice")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Alice")

    def test_patch_updates_phone(self):
        resp = self.client.patch(self.url, {"phone": "9876543210"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["phone"], "9876543210")

    def test_patch_is_partial_preserves_other_fields(self):
        self.user.last_name = "Smith"
        self.user.save()
        resp = self.client.patch(self.url, {"first_name": "Bob"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["last_name"], "Smith")

    def test_patch_cannot_change_role(self):
        from apps.users.constants import UserRole
        resp = self.client.patch(self.url, {"role": UserRole.ADMIN}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, UserRole.WARD_STAFF)
