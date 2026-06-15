from django.contrib import admin

from apps.workflows.models import WorkflowInstance, WorkflowStep, WorkflowTemplate


@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "hospital", "trigger", "is_active", "created_at"]
    list_filter = ["trigger", "is_active", "hospital"]
    search_fields = ["name"]


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(admin.ModelAdmin):
    list_display = ["pk", "template", "admission", "status", "assigned_to", "created_at"]
    list_filter = ["status"]
    search_fields = ["template__name"]


@admin.register(WorkflowStep)
class WorkflowStepAdmin(admin.ModelAdmin):
    list_display = ["instance", "step_index", "title", "is_completed", "completed_by", "completed_at"]
    list_filter = ["is_completed"]
