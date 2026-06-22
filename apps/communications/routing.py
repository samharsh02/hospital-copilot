from django.urls import re_path

from apps.communications.consumer import HospitalConsumer

websocket_urlpatterns = [
    re_path(r"^ws/notifications/$", HospitalConsumer.as_asgi()),
]
