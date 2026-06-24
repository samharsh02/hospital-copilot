from django.db.models import Exists, OuterRef
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import NotFoundError, PermissionDeniedError
from apps.core.exceptions import ValidationError as AppValidationError
from apps.core.helpers import StandardPagination
from apps.patients.models import Admission, Bed, Patient, Ward
from apps.patients.permissions import IsAdminOrAbove, IsNurseOrAbove
from apps.patients.serializers import (
    AdmissionSerializer,
    AdmitSerializer,
    BedCreateSerializer,
    BedSerializer,
    BedUpdateSerializer,
    PatientCreateSerializer,
    PatientSerializer,
    PatientUpdateSerializer,
    WardCreateSerializer,
    WardSerializer,
    WardUpdateSerializer,
)
from apps.patients.services import (
    admit_patient,
    create_bed,
    create_patient,
    create_ward,
    delete_bed,
    discharge_patient,
    get_patient_queryset,
    get_ward_queryset,
    update_bed,
    update_patient,
    update_ward,
)
from apps.users.constants import UserRole


def _get_patient_or_404(pk, user):
    try:
        return get_patient_queryset(user=user).get(pk=pk)
    except Patient.DoesNotExist:
        raise NotFoundError("Patient not found.")


class PatientListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminOrAbove()]
        return [IsAuthenticated()]

    def get(self, request):
        qs = get_patient_queryset(user=request.user)

        if search := request.query_params.get("search", "").strip():
            qs = qs.filter(mrn__icontains=search)

        if ward_id := request.query_params.get("ward"):
            qs = qs.filter(
                admissions__discharged_at__isnull=True,
                admissions__bed__ward_id=ward_id,
            ).distinct()

        active_admission = Admission.objects.filter(patient=OuterRef("pk"), discharged_at__isnull=True)
        status_filter = request.query_params.get("status")
        if status_filter == "active":
            qs = qs.filter(Exists(active_admission))
        elif status_filter == "discharged":
            qs = qs.exclude(Exists(active_admission))

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(PatientSerializer(page, many=True).data)

    def post(self, request):
        serializer = PatientCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hospital = request.user.hospital
        if hospital is None:
            raise PermissionDeniedError("Your account is not associated with a hospital.")
        patient = create_patient(user=request.user, hospital=hospital, **serializer.validated_data)
        return Response(PatientSerializer(patient).data, status=status.HTTP_201_CREATED)


class PatientDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(PatientSerializer(_get_patient_or_404(pk, request.user)).data)

    def patch(self, request, pk):
        if not IsNurseOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Nurse role or above is required.")
        patient = _get_patient_or_404(pk, request.user)
        serializer = PatientUpdateSerializer(patient, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        patient = update_patient(user=request.user, patient=patient, **serializer.validated_data)
        return Response(PatientSerializer(patient).data)

    def delete(self, request, pk):
        if not IsAdminOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Admin role or above is required.")
        patient = _get_patient_or_404(pk, request.user)
        patient.soft_delete(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PatientAdmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        patient = _get_patient_or_404(pk, request.user)
        serializer = AdmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        admission = admit_patient(
            user=request.user,
            patient=patient,
            bed=serializer.validated_data["bed"],
            notes=serializer.validated_data["notes"],
        )
        return Response(AdmissionSerializer(admission).data, status=status.HTTP_201_CREATED)


class PatientDischargeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        patient = _get_patient_or_404(pk, request.user)
        admission = discharge_patient(user=request.user, patient=patient)
        return Response(AdmissionSerializer(admission).data)


class PatientAdmissionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        patient = _get_patient_or_404(pk, request.user)
        admissions = patient.admissions.select_related("bed", "admitted_by").order_by("-admitted_at")
        return Response(AdmissionSerializer(admissions, many=True).data)


class WardListView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminOrAbove()]
        return [IsAuthenticated()]

    def get(self, request):
        return Response(WardSerializer(get_ward_queryset(user=request.user), many=True).data)

    def post(self, request):
        hospital = request.user.hospital
        if hospital is None:
            raise PermissionDeniedError("Your account is not associated with a hospital.")
        serializer = WardCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ward = create_ward(user=request.user, hospital=hospital, **serializer.validated_data)
        return Response(WardSerializer(ward).data, status=status.HTTP_201_CREATED)


class WardDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]
        return [IsAdminOrAbove()]

    def _get_ward_or_404(self, pk):
        try:
            return get_ward_queryset(user=self.request.user).get(pk=pk)
        except Ward.DoesNotExist:
            raise NotFoundError("Ward not found.")

    def get(self, request, pk):
        return Response(WardSerializer(self._get_ward_or_404(pk)).data)

    def patch(self, request, pk):
        ward = self._get_ward_or_404(pk)
        serializer = WardUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ward = update_ward(user=request.user, ward=ward, **serializer.validated_data)
        return Response(WardSerializer(ward).data)

    def delete(self, request, pk):
        ward = self._get_ward_or_404(pk)
        if ward.beds.filter(is_occupied=True).exists():
            raise AppValidationError("Cannot delete a ward with occupied beds.")
        ward.soft_delete(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WardBedsView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminOrAbove()]
        return [IsAuthenticated()]

    def _get_ward_or_404(self, ward_pk):
        try:
            return get_ward_queryset(user=self.request.user).get(pk=ward_pk)
        except Ward.DoesNotExist:
            raise NotFoundError("Ward not found.")

    def get(self, request, ward_pk):
        ward = self._get_ward_or_404(ward_pk)
        return Response(BedSerializer(ward.beds.all(), many=True).data)

    def post(self, request, ward_pk):
        ward = self._get_ward_or_404(ward_pk)
        serializer = BedCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bed = create_bed(user=request.user, ward=ward, **serializer.validated_data)
        return Response(BedSerializer(bed).data, status=status.HTTP_201_CREATED)


class BedDetailView(APIView):
    permission_classes = [IsAdminOrAbove]

    def _get_bed_or_404(self, pk):
        qs = Bed.objects.select_related("ward__hospital")
        if self.request.user.role != UserRole.SUPERADMIN:
            qs = qs.filter(ward__hospital=self.request.user.hospital)
        try:
            return qs.get(pk=pk)
        except Bed.DoesNotExist:
            raise NotFoundError("Bed not found.")

    def patch(self, request, pk):
        bed = self._get_bed_or_404(pk)
        serializer = BedUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bed = update_bed(user=request.user, bed=bed, **serializer.validated_data)
        return Response(BedSerializer(bed).data)

    def delete(self, request, pk):
        bed = self._get_bed_or_404(pk)
        delete_bed(user=request.user, bed=bed)
        return Response(status=status.HTTP_204_NO_CONTENT)
