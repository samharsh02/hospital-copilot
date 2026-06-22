from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing.websocket import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.communications.constants import NotificationKind
from apps.communications.models import Notification
from apps.communications.routing import websocket_urlpatterns
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


def make_app():
    return URLRouter(websocket_urlpatterns)


def comm_for(user):
    token = str(AccessToken.for_user(user))
    return WebsocketCommunicator(make_app(), f"/ws/notifications/?token={token}")


class TestHospitalConsumer(TransactionTestCase):
    def setUp(self):
        self.hospital = make_hospital()
        self.user = make_user("nurse1", hospital=self.hospital)

    # ------------------------------------------------------------------
    # Connection / auth
    # ------------------------------------------------------------------

    def test_connect_valid_token_accepted(self):
        async_to_sync(self._connect_valid_token_accepted)()

    async def _connect_valid_token_accepted(self):
        comm = comm_for(self.user)
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.disconnect()

    def test_connect_invalid_token_rejected(self):
        async_to_sync(self._connect_invalid_token_rejected)()

    async def _connect_invalid_token_rejected(self):
        comm = WebsocketCommunicator(make_app(), "/ws/notifications/?token=not-a-valid-jwt")
        connected, code = await comm.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4001)

    def test_connect_no_token_rejected(self):
        async_to_sync(self._connect_no_token_rejected)()

    async def _connect_no_token_rejected(self):
        comm = WebsocketCommunicator(make_app(), "/ws/notifications/")
        connected, code = await comm.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4001)

    def test_connect_superadmin_no_hospital_rejected(self):
        sa = make_user("sa", role=UserRole.SUPERADMIN)
        async_to_sync(self._connect_superadmin_no_hospital_rejected)(sa)

    async def _connect_superadmin_no_hospital_rejected(self, sa):
        comm = comm_for(sa)
        connected, code = await comm.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4002)

    def test_disconnect_cleans_up_without_error(self):
        async_to_sync(self._disconnect_cleans_up_without_error)()

    async def _disconnect_cleans_up_without_error(self):
        comm = comm_for(self.user)
        await comm.connect()
        await comm.disconnect()

    # ------------------------------------------------------------------
    # Message delivery
    # ------------------------------------------------------------------

    def test_receives_notify_event(self):
        async_to_sync(self._receives_notify_event)()

    async def _receives_notify_event(self):
        comm = comm_for(self.user)
        await comm.connect()
        cl = get_channel_layer()
        await cl.group_send(
            f"hospital_{self.hospital.pk}",
            {"type": "notify", "data": {"kind": "GENERAL", "msg": "hello"}},
        )
        data = await comm.receive_json_from(timeout=3)
        self.assertEqual(data["msg"], "hello")
        await comm.disconnect()

    def test_notify_persists_notification_in_db(self):
        async_to_sync(self._notify_persists_notification_in_db)()

    async def _notify_persists_notification_in_db(self):
        comm = comm_for(self.user)
        await comm.connect()
        cl = get_channel_layer()
        await cl.group_send(
            f"hospital_{self.hospital.pk}",
            {"type": "notify", "data": {"kind": "ESCALATION", "alert_id": 99}},
        )
        await comm.receive_json_from(timeout=3)
        await comm.disconnect()
        count = await sync_to_async(Notification.objects.filter(user=self.user).count)()
        self.assertEqual(count, 1)

    def test_persisted_notification_has_correct_kind(self):
        async_to_sync(self._persisted_notification_has_correct_kind)()

    async def _persisted_notification_has_correct_kind(self):
        comm = comm_for(self.user)
        await comm.connect()
        cl = get_channel_layer()
        await cl.group_send(
            f"hospital_{self.hospital.pk}",
            {"type": "notify", "data": {"kind": "ESCALATION"}},
        )
        await comm.receive_json_from(timeout=3)
        await comm.disconnect()
        get_n = sync_to_async(lambda: Notification.objects.get(user=self.user))
        n = await get_n()
        self.assertEqual(n.kind, NotificationKind.ESCALATION)

    def test_message_not_received_by_other_hospital_user(self):
        h2 = make_hospital("H2")
        user2 = make_user("user2", hospital=h2)
        async_to_sync(self._message_not_received_by_other_hospital_user)(user2)

    async def _message_not_received_by_other_hospital_user(self, user2):
        comm1 = comm_for(self.user)
        comm2 = comm_for(user2)
        await comm1.connect()
        await comm2.connect()
        cl = get_channel_layer()
        await cl.group_send(
            f"hospital_{self.hospital.pk}",
            {"type": "notify", "data": {"kind": "GENERAL"}},
        )
        resp = await comm1.receive_json_from(timeout=3)
        self.assertIsNotNone(resp)
        nothing = await comm2.receive_nothing(timeout=0.5)
        self.assertTrue(nothing)
        await comm1.disconnect()
        await comm2.disconnect()
