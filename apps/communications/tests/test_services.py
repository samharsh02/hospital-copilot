from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.communications.constants import NotificationKind
from apps.communications.models import Notification
from apps.communications.services import (
    get_notification_queryset,
    mark_all_notifications_read,
    mark_notification_read,
)
from apps.core.constants import HospitalType
from apps.core.exceptions import NotFoundError
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


def make_notification(user, hospital, kind=NotificationKind.GENERAL, payload=None):
    return Notification.objects.create(
        user=user, hospital=hospital,
        kind=kind, payload=payload or {},
        created_by=user, updated_by=user,
    )


class TestGetNotificationQueryset(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user("u1", hospital=self.hospital)
        self.other = make_user("u2", hospital=self.hospital)
        make_notification(self.user, self.hospital)
        make_notification(self.other, self.hospital)

    def test_returns_own_notifications_only(self):
        qs = get_notification_queryset(user=self.user)
        self.assertEqual(qs.count(), 1)

    def test_excludes_other_user_notifications(self):
        qs = get_notification_queryset(user=self.other)
        pks = list(qs.values_list("user_id", flat=True))
        self.assertTrue(all(pk == self.other.pk for pk in pks))

    def test_returns_all_kinds(self):
        make_notification(self.user, self.hospital, kind=NotificationKind.ESCALATION)
        qs = get_notification_queryset(user=self.user)
        self.assertEqual(qs.count(), 2)


class TestMarkNotificationRead(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user("u1", hospital=self.hospital)
        self.n = make_notification(self.user, self.hospital)

    def test_sets_read_at(self):
        result = mark_notification_read(user=self.user, notification_id=self.n.pk)
        self.assertIsNotNone(result.read_at)

    def test_is_read_property_true_after_mark(self):
        result = mark_notification_read(user=self.user, notification_id=self.n.pk)
        self.assertTrue(result.is_read)

    def test_idempotent_on_already_read(self):
        mark_notification_read(user=self.user, notification_id=self.n.pk)
        self.n.refresh_from_db()
        first_read_at = self.n.read_at
        result = mark_notification_read(user=self.user, notification_id=self.n.pk)
        self.assertEqual(result.read_at, first_read_at)

    def test_wrong_user_raises_not_found(self):
        other = make_user("other", hospital=self.hospital)
        with self.assertRaises(NotFoundError):
            mark_notification_read(user=other, notification_id=self.n.pk)

    def test_nonexistent_id_raises_not_found(self):
        with self.assertRaises(NotFoundError):
            mark_notification_read(user=self.user, notification_id=99999)


class TestMarkAllNotificationsRead(TestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user("u1", hospital=self.hospital)
        self.other = make_user("u2", hospital=self.hospital)
        for _ in range(3):
            make_notification(self.user, self.hospital)
        make_notification(self.other, self.hospital)

    def test_marks_all_own_unread(self):
        mark_all_notifications_read(user=self.user)
        unread = Notification.objects.filter(user=self.user, read_at__isnull=True).count()
        self.assertEqual(unread, 0)

    def test_does_not_affect_other_user(self):
        mark_all_notifications_read(user=self.user)
        unread_other = Notification.objects.filter(user=self.other, read_at__isnull=True).count()
        self.assertEqual(unread_other, 1)

    def test_already_read_not_overwritten(self):
        mark_all_notifications_read(user=self.user)
        first_read_ats = list(Notification.objects.filter(user=self.user).values_list("read_at", flat=True))
        mark_all_notifications_read(user=self.user)
        second_read_ats = list(Notification.objects.filter(user=self.user).values_list("read_at", flat=True))
        self.assertEqual(first_read_ats, second_read_ats)
