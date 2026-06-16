from django.contrib import admin

from apps.intelligence.models import IntelligenceRequest


@admin.register(IntelligenceRequest)
class IntelligenceRequestAdmin(admin.ModelAdmin):
    list_display = [
        "id", "patient", "prompt_type", "status",
        "clinical_context_used", "tokens_used", "latency_ms", "created_at",
    ]
    list_filter = ["prompt_type", "status", "clinical_context_used"]
    search_fields = ["patient__mrn"]
    readonly_fields = [
        "patient", "admission", "requested_by", "prompt_type", "status",
        "clinical_context_used", "response_text", "disclaimer",
        "tokens_used", "latency_ms", "completed_at", "created_at",
    ]
