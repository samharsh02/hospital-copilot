from django.utils.timezone import now

from apps.communications.models import Notification
from apps.core.exceptions import NotFoundError


def get_notification_queryset(*, user):
    return Notification.objects.filter(user=user).select_related("hospital")


def mark_notification_read(*, user, notification_id: int) -> Notification:
    try:
        n = Notification.objects.get(pk=notification_id, user=user)
    except Notification.DoesNotExist:
        raise NotFoundError("Notification not found.")
    if n.read_at is None:
        n.read_at = now()
        n.save(update_fields=["read_at"])
    return n


def mark_all_notifications_read(*, user) -> None:
    Notification.objects.filter(user=user, read_at__isnull=True).update(read_at=now())
