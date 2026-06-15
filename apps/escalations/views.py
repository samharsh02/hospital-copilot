from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import NotFoundError, PermissionDeniedError
from apps.core.helpers import StandardPagination
from apps.escalations.constants import AlertStatus
from apps.escalations.models import EscalationAlert, EscalationRule
from apps.escalations.serializers import (
    EscalationAlertSerializer,
    EscalationRuleCreateSerializer,
    EscalationRuleSerializer,
    EscalationRuleUpdateSerializer,
)
from apps.escalations.services import (
    acknowledge_alert,
    create_rule,
    get_alert_queryset,
    get_rule_queryset,
    resolve_alert,
    update_rule,
)
from apps.patients.permissions import IsAdminOrAbove, IsNurseOrAbove


def _make_role_perm(min_role):
    from apps.patients.permissions import ROLE_RANK
    from rest_framework.permissions import BasePermission

    class _P(BasePermission):
        def has_permission(self, request, view):
            return (
                request.user
                and request.user.is_authenticated
                and ROLE_RANK.get(getattr(request.user, "role", ""), 0) >= ROLE_RANK[min_role]
            )
    _P.__name__ = f"Is{min_role.capitalize()}OrAbove"
    return _P


IsDoctorOrAbove = _make_role_perm("DOCTOR")


def _get_rule_or_404(pk, user):
    try:
        return get_rule_queryset(user=user).get(pk=pk)
    except EscalationRule.DoesNotExist:
        raise NotFoundError("Escalation rule not found.")


def _get_alert_or_404(pk, user):
    try:
        return get_alert_queryset(user=user).get(pk=pk)
    except EscalationAlert.DoesNotExist:
        raise NotFoundError("Escalation alert not found.")


class EscalationRuleListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not IsAdminOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Admin role or above is required.")
        qs = get_rule_queryset(user=request.user)
        if active := request.query_params.get("active"):
            qs = qs.filter(is_active=active.lower() == "true")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(EscalationRuleSerializer(page, many=True).data)

    def post(self, request):
        if not IsAdminOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Admin role or above is required.")
        hospital = request.user.hospital
        if hospital is None:
            raise PermissionDeniedError("Your account is not associated with a hospital.")
        serializer = EscalationRuleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = create_rule(user=request.user, hospital=hospital, **serializer.validated_data)
        return Response(EscalationRuleSerializer(rule).data, status=status.HTTP_201_CREATED)


class EscalationRuleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not IsAdminOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Admin role or above is required.")
        return Response(EscalationRuleSerializer(_get_rule_or_404(pk, request.user)).data)

    def patch(self, request, pk):
        if not IsAdminOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Admin role or above is required.")
        rule = _get_rule_or_404(pk, request.user)
        serializer = EscalationRuleUpdateSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        rule = update_rule(user=request.user, rule=rule, **serializer.validated_data)
        return Response(EscalationRuleSerializer(rule).data)

    def delete(self, request, pk):
        if not IsAdminOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Admin role or above is required.")
        rule = _get_rule_or_404(pk, request.user)
        rule.soft_delete(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EscalationAlertListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = get_alert_queryset(user=request.user)
        if status_filter := request.query_params.get("status"):
            qs = qs.filter(status=status_filter.upper())
        if patient_id := request.query_params.get("patient"):
            qs = qs.filter(patient_id=patient_id)
        if admission_id := request.query_params.get("admission"):
            qs = qs.filter(admission_id=admission_id)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(EscalationAlertSerializer(page, many=True).data)


class AcknowledgeAlertView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not IsNurseOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Nurse role or above is required.")
        alert = _get_alert_or_404(pk, request.user)
        alert = acknowledge_alert(user=request.user, alert=alert)
        return Response(EscalationAlertSerializer(alert).data)


class ResolveAlertView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not IsDoctorOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Doctor role or above is required.")
        alert = _get_alert_or_404(pk, request.user)
        alert = resolve_alert(user=request.user, alert=alert)
        return Response(EscalationAlertSerializer(alert).data)
