from django.contrib import admin

from apps.escalations.models import EscalationAlert, EscalationRule


@admin.register(EscalationRule)
class EscalationRuleAdmin(admin.ModelAdmin):
    list_display = ["name", "hospital", "priority", "is_active", "created_at"]
    list_filter = ["priority", "is_active", "hospital"]
    search_fields = ["name"]


@admin.register(EscalationAlert)
class EscalationAlertAdmin(admin.ModelAdmin):
    list_display = ["pk", "rule", "patient", "status", "triggered_at", "acknowledged_by"]
    list_filter = ["status", "rule__priority"]
    date_hierarchy = "triggered_at"
