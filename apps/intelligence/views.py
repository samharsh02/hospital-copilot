from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import NotFoundError
from apps.core.helpers import StandardPagination
from apps.intelligence.models import IntelligenceRequest
from apps.intelligence.serializers import (
    IntelligenceQueryCreateSerializer,
    IntelligenceRequestSerializer,
)
from apps.intelligence.services import get_request_queryset, request_ai_query
from apps.patients.models import Admission, Patient
from apps.patients.permissions import IsAdminOrAbove


class QueryCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrAbove]

    def post(self, request):
        serializer = IntelligenceQueryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Resolve patient and admission within the user's hospital scope.
        try:
            if request.user.role == "SUPERADMIN":
                patient = Patient.objects.get(pk=data["patient"])
            else:
                patient = Patient.objects.get(pk=data["patient"], hospital=request.user.hospital)
        except Patient.DoesNotExist:
            raise NotFoundError("Patient not found.")

        try:
            admission = Admission.objects.get(pk=data["admission"], patient=patient)
        except Admission.DoesNotExist:
            raise NotFoundError("Admission not found.")

        req = request_ai_query(
            user=request.user,
            patient=patient,
            admission=admission,
            prompt_type=data["prompt_type"],
        )
        return Response(
            IntelligenceRequestSerializer(req).data,
            status=status.HTTP_202_ACCEPTED,
        )


class QueryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            req = get_request_queryset(user=request.user).get(pk=pk)
        except IntelligenceRequest.DoesNotExist:
            raise NotFoundError("Intelligence request not found.")
        return Response(IntelligenceRequestSerializer(req).data)


class PatientIntelligenceHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            if request.user.role == "SUPERADMIN":
                patient = Patient.objects.get(pk=pk)
            else:
                patient = Patient.objects.get(pk=pk, hospital=request.user.hospital)
        except Patient.DoesNotExist:
            raise NotFoundError("Patient not found.")

        qs = get_request_queryset(user=request.user).filter(patient=patient)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(
            IntelligenceRequestSerializer(page, many=True).data
        )
