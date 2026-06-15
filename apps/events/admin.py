from django.contrib import admin

from apps.events.models import ClinicalEvent


@admin.register(ClinicalEvent)
class ClinicalEventAdmin(admin.ModelAdmin):
    list_display = ["id", "patient", "admission", "event_type", "recorded_by", "recorded_at"]
    list_filter = ["event_type"]
    search_fields = ["patient__mrn", "notes"]
    date_hierarchy = "recorded_at"
