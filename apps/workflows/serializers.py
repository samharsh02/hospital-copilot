from rest_framework import serializers

from apps.patients.models import Admission
from apps.workflows.constants import InstanceStatus, WorkflowTrigger
from apps.workflows.models import WorkflowInstance, WorkflowStep, WorkflowTemplate


class WorkflowStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowStep
        fields = [
            "id", "step_index", "title", "is_completed",
            "completed_by", "completed_at", "notes", "created_at",
        ]
        read_only_fields = fields


class WorkflowTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowTemplate
        fields = [
            "id", "name", "hospital", "steps", "trigger", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class WorkflowTemplateCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    steps = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    trigger = serializers.ChoiceField(choices=WorkflowTrigger.choices, default=WorkflowTrigger.MANUAL)
    is_active = serializers.BooleanField(default=True)


class WorkflowTemplateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowTemplate
        fields = ["name", "steps", "trigger", "is_active"]


class WorkflowInstanceSerializer(serializers.ModelSerializer):
    steps = WorkflowStepSerializer(many=True, read_only=True)

    class Meta:
        model = WorkflowInstance
        fields = [
            "id", "template", "admission", "status", "assigned_to",
            "started_at", "completed_at", "steps", "created_at",
        ]
        read_only_fields = fields


class StartWorkflowSerializer(serializers.Serializer):
    template = serializers.PrimaryKeyRelatedField(queryset=WorkflowTemplate.objects.all())
    admission = serializers.PrimaryKeyRelatedField(queryset=Admission.objects.all())
    assigned_to_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class CompleteStepSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")
