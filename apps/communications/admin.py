from django.contrib import admin

from apps.communications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "kind", "is_read", "created_at"]
    list_filter = ["kind"]
    readonly_fields = ["user", "hospital", "kind", "payload", "read_at", "created_at"]
