from rest_framework import serializers

from apps.escalations.constants import AlertPriority, AlertStatus
from apps.escalations.models import EscalationAlert, EscalationRule


class EscalationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = EscalationRule
        fields = [
            "id", "hospital", "name", "condition", "priority",
            "notify_roles", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class EscalationRuleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    condition = serializers.DictField()
    priority = serializers.ChoiceField(choices=AlertPriority.choices)
    notify_roles = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    is_active = serializers.BooleanField(default=True)


class EscalationRuleUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EscalationRule
        fields = ["name", "condition", "priority", "notify_roles", "is_active"]


class EscalationAlertSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source="rule.name", read_only=True)
    priority = serializers.CharField(source="rule.priority", read_only=True)

    class Meta:
        model = EscalationAlert
        fields = [
            "id", "rule", "rule_name", "priority", "patient", "admission",
            "triggered_at", "status",
            "acknowledged_at", "acknowledged_by",
            "resolved_at", "created_at",
        ]
        read_only_fields = fields
