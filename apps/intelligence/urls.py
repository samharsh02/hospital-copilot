from django.urls import path

from apps.intelligence.views import (
    PatientIntelligenceHistoryView,
    QueryCreateView,
    QueryDetailView,
)

urlpatterns = [
    path("intelligence/query/", QueryCreateView.as_view(), name="intelligence-query-create"),
    path("intelligence/<int:pk>/", QueryDetailView.as_view(), name="intelligence-query-detail"),
    path("patients/<int:pk>/intelligence/", PatientIntelligenceHistoryView.as_view(), name="patient-intelligence-history"),
]
