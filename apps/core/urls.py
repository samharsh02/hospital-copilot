from django.urls import path

from apps.core.views import HospitalDetailView

urlpatterns = [
    path("hospital/", HospitalDetailView.as_view(), name="hospital-detail"),
]
