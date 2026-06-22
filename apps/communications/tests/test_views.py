from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.communications.constants import NotificationKind
from apps.communications.models import Notification
from apps.core.constants import HospitalType
from apps.core.models import Hospital
from apps.users.constants import UserRole

User = get_user_model()


def make_hospital(name="H1"):
    return Hospital.all_objects.create(
        name=name, type=HospitalType.PRIVATE_SINGLE,
        city="Delhi", state="Delhi", bed_count=50,
    )


def make_user(username, role=UserRole.NURSE, hospital=None):
    return User.objects.create_user(username=username, password="Pass1234!", role=role, hospital=hospital)


def make_notification(user, hospital, kind=NotificationKind.GENERAL):
    return Notification.objects.create(
        user=user, hospital=hospital, kind=kind, payload={},
        created_by=user, updated_by=user,
    )


def auth_client(user):
    client = APIClient()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


# ---------------------------------------------------------------------------
# GET /api/v1/notifications/
# ---------------------------------------------------------------------------

class TestNotificationListView(APITestCase):
    url = "/api/v1/notifications/"

    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user("u1", hospital=self.hospital)
        self.other = make_user("u2", hospital=self.hospital)
        make_notification(self.user, self.hospital)
        make_notification(self.user, self.hospital, kind=NotificationKind.ESCALATION)
        make_notification(self.other, self.hospital)

    def test_returns_own_notifications_only(self):
        resp = auth_client(self.user).get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    def test_does_not_bleed_other_user(self):
        resp = auth_client(self.other).get(self.url)
        self.assertEqual(resp.data["count"], 1)

    def test_unread_filter_excludes_read(self):
        n = Notification.objects.filter(user=self.user).first()
        from django.utils.timezone import now
        n.read_at = now()
        n.save()
        resp = auth_client(self.user).get(self.url + "?unread=true")
        self.assertEqual(resp.data["count"], 1)

    def test_no_unread_param_returns_all(self):
        n = Notification.objects.filter(user=self.user).first()
        from django.utils.timezone import now
        n.read_at = now()
        n.save()
        resp = auth_client(self.user).get(self.url)
        self.assertEqual(resp.data["count"], 2)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_response_includes_is_read_field(self):
        resp = auth_client(self.user).get(self.url)
        self.assertIn("is_read", resp.data["results"][0])


# ---------------------------------------------------------------------------
# POST /api/v1/notifications/<pk>/read/
# ---------------------------------------------------------------------------

class TestNotificationReadView(APITestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user("u1", hospital=self.hospital)
        self.n = make_notification(self.user, self.hospital)

    def url(self, pk=None):
        return f"/api/v1/notifications/{pk or self.n.pk}/read/"

    def test_marks_notification_read(self):
        resp = auth_client(self.user).post(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["is_read"])
        self.assertIsNotNone(resp.data["read_at"])

    def test_idempotent(self):
        auth_client(self.user).post(self.url())
        resp = auth_client(self.user).post(self.url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_wrong_user_returns_404(self):
        other = make_user("other", hospital=self.hospital)
        resp = auth_client(other).post(self.url())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonexistent_returns_404(self):
        resp = auth_client(self.user).post(self.url(99999))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().post(self.url())
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# POST /api/v1/notifications/read-all/
# ---------------------------------------------------------------------------

class TestNotificationReadAllView(APITestCase):
    url = "/api/v1/notifications/read-all/"

    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user("u1", hospital=self.hospital)
        self.other = make_user("u2", hospital=self.hospital)
        for _ in range(3):
            make_notification(self.user, self.hospital)
        make_notification(self.other, self.hospital)

    def test_marks_all_read_returns_200(self):
        resp = auth_client(self.user).post(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_all_user_notifications_marked_read(self):
        auth_client(self.user).post(self.url)
        unread = Notification.objects.filter(user=self.user, read_at__isnull=True).count()
        self.assertEqual(unread, 0)

    def test_other_user_notifications_unaffected(self):
        auth_client(self.user).post(self.url)
        unread_other = Notification.objects.filter(user=self.other, read_at__isnull=True).count()
        self.assertEqual(unread_other, 1)

    def test_unauthenticated_returns_401(self):
        resp = self.client_class().post(self.url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
