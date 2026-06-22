from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.communications.constants import NotificationKind

_VALID_KINDS = {k for k, _ in NotificationKind.choices}


class HospitalConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        params = parse_qs(self.scope.get("query_string", b"").decode())
        token_list = params.get("token", [])
        if not token_list:
            await self.close(code=4001)
            return

        user = await _get_user_from_token(token_list[0])
        if user is None:
            await self.close(code=4001)
            return

        if not user.hospital_id:
            await self.close(code=4002)
            return

        self.scope["user"] = user
        self.hospital_group = f"hospital_{user.hospital_id}"
        await self.channel_layer.group_add(self.hospital_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "hospital_group"):
            await self.channel_layer.group_discard(self.hospital_group, self.channel_name)

    async def notify(self, event):
        data = event["data"]
        user = self.scope.get("user")
        if user:
            await _create_notification(user, data)
        await self.send_json(data)


@database_sync_to_async
def _get_user_from_token(token_str: str):
    from django.contrib.auth import get_user_model
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    User = get_user_model()
    try:
        token = AccessToken(token_str)
        user_id = token.get("user_id")
        if user_id is None:
            return None
        return User.objects.select_related("hospital").get(pk=user_id, is_active=True)
    except (TokenError, Exception):
        return None


@database_sync_to_async
def _create_notification(user, data: dict) -> None:
    from apps.communications.models import Notification

    kind = data.get("kind", NotificationKind.GENERAL)
    if kind not in _VALID_KINDS:
        kind = NotificationKind.GENERAL

    Notification.objects.create(
        user=user,
        hospital=user.hospital,
        kind=kind,
        payload=data,
        created_by=user,
        updated_by=user,
    )
