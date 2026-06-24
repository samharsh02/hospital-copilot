from rest_framework import serializers

from apps.core.models import Hospital


class HospitalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hospital
        fields = [
            "id", "name", "type", "city", "state", "bed_count",
            "is_active", "clinical_module_enabled", "created_at",
        ]
        read_only_fields = fields
