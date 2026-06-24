from django.urls import path

from apps.events.views import PatientEventTimelineView
from apps.patients.views import (
    BedDetailView,
    PatientAdmissionsView,
    PatientAdmitView,
    PatientDetailView,
    PatientDischargeView,
    PatientListCreateView,
    WardBedsView,
    WardDetailView,
    WardListView,
)

urlpatterns = [
    path("patients/", PatientListCreateView.as_view(), name="patient-list-create"),
    path("patients/<int:pk>/", PatientDetailView.as_view(), name="patient-detail"),
    path("patients/<int:pk>/admit/", PatientAdmitView.as_view(), name="patient-admit"),
    path("patients/<int:pk>/discharge/", PatientDischargeView.as_view(), name="patient-discharge"),
    path("patients/<int:pk>/admissions/", PatientAdmissionsView.as_view(), name="patient-admissions"),
    path("patients/<int:pk>/events/", PatientEventTimelineView.as_view(), name="patient-events"),
    path("wards/", WardListView.as_view(), name="ward-list"),
    path("wards/<int:pk>/", WardDetailView.as_view(), name="ward-detail"),
    path("wards/<int:ward_pk>/beds/", WardBedsView.as_view(), name="ward-beds"),
    path("beds/<int:pk>/", BedDetailView.as_view(), name="bed-detail"),
]
