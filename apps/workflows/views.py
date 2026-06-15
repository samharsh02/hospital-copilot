from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import NotFoundError, PermissionDeniedError
from apps.core.helpers import StandardPagination
from apps.patients.permissions import IsAdminOrAbove, IsNurseOrAbove
from apps.users.constants import UserRole
from apps.workflows.models import WorkflowInstance, WorkflowTemplate
from apps.workflows.serializers import (
    CompleteStepSerializer,
    StartWorkflowSerializer,
    WorkflowInstanceSerializer,
    WorkflowTemplateCreateSerializer,
    WorkflowTemplateSerializer,
    WorkflowTemplateUpdateSerializer,
)
from apps.workflows.services import (
    cancel_workflow,
    complete_step,
    create_template,
    get_instance_queryset,
    get_template_queryset,
    start_workflow,
    update_template,
)

User = get_user_model()


def _get_template_or_404(pk, user):
    try:
        return get_template_queryset(user=user).get(pk=pk)
    except WorkflowTemplate.DoesNotExist:
        raise NotFoundError("Workflow template not found.")


def _get_instance_or_404(pk, user):
    try:
        return get_instance_queryset(user=user).prefetch_related("steps").get(pk=pk)
    except WorkflowInstance.DoesNotExist:
        raise NotFoundError("Workflow instance not found.")


class WorkflowTemplateListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = get_template_queryset(user=request.user)
        if active := request.query_params.get("active"):
            qs = qs.filter(is_active=active.lower() == "true")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(WorkflowTemplateSerializer(page, many=True).data)

    def post(self, request):
        if not IsAdminOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Admin role or above is required.")
        hospital = request.user.hospital
        if hospital is None:
            raise PermissionDeniedError("Your account is not associated with a hospital.")
        serializer = WorkflowTemplateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = create_template(user=request.user, hospital=hospital, **serializer.validated_data)
        return Response(WorkflowTemplateSerializer(template).data, status=status.HTTP_201_CREATED)


class WorkflowTemplateDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(WorkflowTemplateSerializer(_get_template_or_404(pk, request.user)).data)

    def patch(self, request, pk):
        if not IsAdminOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Admin role or above is required.")
        template = _get_template_or_404(pk, request.user)
        serializer = WorkflowTemplateUpdateSerializer(template, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        template = update_template(user=request.user, template=template, **serializer.validated_data)
        return Response(WorkflowTemplateSerializer(template).data)

    def delete(self, request, pk):
        if not IsAdminOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Admin role or above is required.")
        template = _get_template_or_404(pk, request.user)
        template.soft_delete(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkflowInstanceListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = get_instance_queryset(user=request.user).prefetch_related("steps")
        if template_id := request.query_params.get("template"):
            qs = qs.filter(template_id=template_id)
        if admission_id := request.query_params.get("admission"):
            qs = qs.filter(admission_id=admission_id)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(WorkflowInstanceSerializer(page, many=True).data)

    def post(self, request):
        if not IsNurseOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Nurse role or above is required.")
        serializer = StartWorkflowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assigned_to = None
        if serializer.validated_data["assigned_to_id"] is not None:
            try:
                assigned_to = User.objects.get(pk=serializer.validated_data["assigned_to_id"])
            except User.DoesNotExist:
                raise NotFoundError("Assigned user not found.")

        instance = start_workflow(
            user=request.user,
            template=serializer.validated_data["template"],
            admission=serializer.validated_data["admission"],
            assigned_to=assigned_to,
        )
        instance = _get_instance_or_404(instance.pk, request.user)
        return Response(WorkflowInstanceSerializer(instance).data, status=status.HTTP_201_CREATED)


class WorkflowInstanceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(WorkflowInstanceSerializer(_get_instance_or_404(pk, request.user)).data)


class CompleteStepView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, step_index):
        if not IsNurseOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Nurse role or above is required.")
        instance = _get_instance_or_404(pk, request.user)
        serializer = CompleteStepSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        step = complete_step(
            user=request.user,
            instance=instance,
            step_index=step_index,
            notes=serializer.validated_data["notes"],
        )
        from apps.workflows.serializers import WorkflowStepSerializer
        return Response(WorkflowStepSerializer(step).data)


class CancelWorkflowView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not IsNurseOrAbove().has_permission(request, self):
            raise PermissionDeniedError("Nurse role or above is required.")
        instance = _get_instance_or_404(pk, request.user)
        instance = cancel_workflow(user=request.user, instance=instance)
        return Response(WorkflowInstanceSerializer(instance).data)
