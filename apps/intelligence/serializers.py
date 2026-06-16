from rest_framework import serializers

from apps.intelligence.constants import PromptType
from apps.intelligence.models import IntelligenceRequest


class IntelligenceRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntelligenceRequest
        fields = [
            "id", "patient", "admission", "requested_by", "prompt_type",
            "status", "clinical_context_used",
            "response_text", "disclaimer",
            "tokens_used", "latency_ms",
            "created_at", "completed_at",
        ]
        read_only_fields = fields


class IntelligenceQueryCreateSerializer(serializers.Serializer):
    patient = serializers.IntegerField()
    admission = serializers.IntegerField()
    prompt_type = serializers.ChoiceField(choices=PromptType.choices)
