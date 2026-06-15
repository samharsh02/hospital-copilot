from django.urls import path

from apps.escalations.views import (
    AcknowledgeAlertView,
    EscalationAlertListView,
    EscalationRuleDetailView,
    EscalationRuleListCreateView,
    ResolveAlertView,
)

urlpatterns = [
    path("escalation-rules/", EscalationRuleListCreateView.as_view(), name="escalation-rule-list-create"),
    path("escalation-rules/<int:pk>/", EscalationRuleDetailView.as_view(), name="escalation-rule-detail"),
    path("escalation-alerts/", EscalationAlertListView.as_view(), name="escalation-alert-list"),
    path("escalation-alerts/<int:pk>/acknowledge/", AcknowledgeAlertView.as_view(), name="escalation-alert-acknowledge"),
    path("escalation-alerts/<int:pk>/resolve/", ResolveAlertView.as_view(), name="escalation-alert-resolve"),
]
