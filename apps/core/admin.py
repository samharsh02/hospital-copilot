from django.contrib import admin

from apps.core.models import Hospital


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ["name", "type", "city", "state", "bed_count", "clinical_module_enabled", "is_active"]
    list_filter = ["type", "clinical_module_enabled", "is_active", "state"]
    search_fields = ["name", "city"]
    list_editable = ["clinical_module_enabled", "is_active"]
