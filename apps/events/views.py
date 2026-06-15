from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import NotFoundError, PermissionDeniedError
from apps.core.helpers import StandardPagination
from apps.events.constants import EventType
from apps.events.serializers import ClinicalEventSerializer, RecordEventSerializer
from apps.events.services import get_event_queryset, record_event
from apps.patients.permissions import IsNurseOrAbove
from apps.patients.services import get_patient_queryset
from apps.patients.models import Patient


def _get_patient_or_404(pk, user):
    try:
        return get_patient_queryset(user=user).get(pk=pk)
    except Patient.DoesNotExist:
        raise NotFoundError("Patient not found.")


class EventListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = get_event_queryset(user=request.user)

        if patient_id := request.query_params.get("patient"):
            qs = qs.filter(patient_id=patient_id)
        if admission_id := request.query_params.get("admission"):
            qs = qs.filter(admission_id=admission_id)
        if event_type := request.query_params.get("event_type"):
            qs = qs.filter(event_type=event_type)
        if date_from := request.query_params.get("date_from"):
            qs = qs.filter(recorded_at__date__gte=date_from)
        if date_to := request.query_params.get("date_to"):
            qs = qs.filter(recorded_at__date__lte=date_to)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(ClinicalEventSerializer(page, many=True).data)

    def post(self, request):
        if not IsNurseOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Nurse role or above is required.")
        serializer = RecordEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = record_event(user=request.user, **serializer.validated_data)
        return Response(ClinicalEventSerializer(event).data, status=status.HTTP_201_CREATED)


class PatientEventTimelineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        patient = _get_patient_or_404(pk, request.user)
        qs = get_event_queryset(user=request.user, patient=patient)

        if event_type := request.query_params.get("event_type"):
            qs = qs.filter(event_type=event_type)
        if date_from := request.query_params.get("date_from"):
            qs = qs.filter(recorded_at__date__gte=date_from)
        if date_to := request.query_params.get("date_to"):
            qs = qs.filter(recorded_at__date__lte=date_to)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(ClinicalEventSerializer(page, many=True).data)
