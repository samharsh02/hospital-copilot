from rest_framework import serializers

from apps.events.constants import EventType
from apps.events.models import ClinicalEvent
from apps.patients.models import Admission, Patient


class ClinicalEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicalEvent
        fields = [
            "id", "patient", "admission", "event_type",
            "recorded_by", "recorded_at", "payload", "notes", "created_at",
        ]
        read_only_fields = fields


class RecordEventSerializer(serializers.Serializer):
    patient = serializers.PrimaryKeyRelatedField(queryset=Patient.objects.all())
    admission = serializers.PrimaryKeyRelatedField(queryset=Admission.objects.all())
    event_type = serializers.ChoiceField(choices=EventType.choices)
    payload = serializers.DictField(required=False, default=dict)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
