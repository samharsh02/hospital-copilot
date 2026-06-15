from rest_framework import serializers

from apps.patients.constants import BloodGroup, Gender
from apps.patients.models import Admission, Bed, Patient, Ward


class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = [
            "id", "mrn", "first_name", "last_name", "date_of_birth", "gender",
            "blood_group", "contact_phone", "emergency_contact_name",
            "emergency_contact_phone", "hospital", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PatientCreateSerializer(serializers.Serializer):
    mrn = serializers.CharField(max_length=50)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    date_of_birth = serializers.DateField()
    gender = serializers.ChoiceField(choices=Gender.choices)
    blood_group = serializers.ChoiceField(choices=BloodGroup.choices, required=False, allow_blank=True, default="")
    contact_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    emergency_contact_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    emergency_contact_phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")


class PatientUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = [
            "blood_group", "contact_phone", "emergency_contact_name",
            "emergency_contact_phone", "is_active",
        ]


class WardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ward
        fields = ["id", "name", "hospital", "capacity", "created_at"]
        read_only_fields = ["id", "created_at"]


class BedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bed
        fields = ["id", "number", "ward", "is_occupied"]
        read_only_fields = ["id"]


class AdmissionSerializer(serializers.ModelSerializer):
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Admission
        fields = [
            "id", "patient", "bed", "admitted_by", "admitted_at",
            "discharged_at", "notes", "is_active", "created_at",
        ]
        read_only_fields = [
            "id", "patient", "admitted_by", "admitted_at",
            "discharged_at", "created_at", "is_active",
        ]


class AdmitSerializer(serializers.Serializer):
    bed = serializers.PrimaryKeyRelatedField(
        queryset=Bed.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
