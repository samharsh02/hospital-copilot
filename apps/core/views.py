from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import NotFoundError
from apps.core.serializers import HospitalSerializer


class HospitalDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.hospital is None:
            raise NotFoundError("No hospital is associated with this account.")
        return Response(HospitalSerializer(request.user.hospital).data)
