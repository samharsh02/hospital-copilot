from django.urls import path

from apps.workflows.views import (
    CancelWorkflowView,
    CompleteStepView,
    WorkflowInstanceDetailView,
    WorkflowInstanceListCreateView,
    WorkflowTemplateDetailView,
    WorkflowTemplateListCreateView,
)

urlpatterns = [
    path("workflow-templates/", WorkflowTemplateListCreateView.as_view(), name="workflow-template-list-create"),
    path("workflow-templates/<int:pk>/", WorkflowTemplateDetailView.as_view(), name="workflow-template-detail"),
    path("workflow-instances/", WorkflowInstanceListCreateView.as_view(), name="workflow-instance-list-create"),
    path("workflow-instances/<int:pk>/", WorkflowInstanceDetailView.as_view(), name="workflow-instance-detail"),
    path("workflow-instances/<int:pk>/steps/<int:step_index>/complete/", CompleteStepView.as_view(), name="workflow-step-complete"),
    path("workflow-instances/<int:pk>/cancel/", CancelWorkflowView.as_view(), name="workflow-instance-cancel"),
]
