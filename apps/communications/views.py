from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.communications.serializers import NotificationSerializer
from apps.communications.services import (
    get_notification_queryset,
    mark_all_notifications_read,
    mark_notification_read,
)
from apps.core.helpers import StandardPagination


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = get_notification_queryset(user=request.user)
        if request.query_params.get("unread") == "true":
            qs = qs.filter(read_at__isnull=True)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(NotificationSerializer(page, many=True).data)


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        n = mark_notification_read(user=request.user, notification_id=pk)
        return Response(NotificationSerializer(n).data)


class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        mark_all_notifications_read(user=request.user)
        return Response({"detail": "All notifications marked as read."})
