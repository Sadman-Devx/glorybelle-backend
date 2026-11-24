from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .emails import send_shop_notification
from .models import Enquiry
from .serializers import EnquiryCreateSerializer
from .throttling import EnquiryCreateRateThrottle


class EnquiryCreateView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [EnquiryCreateRateThrottle]
    serializer_class = EnquiryCreateSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        honeypot = data.pop("website", "")
        if not honeypot:
            enquiry = Enquiry.objects.create(**data)
            send_shop_notification(enquiry)

        return Response(
            {
                "message": (
                    "Grazie per aver contattato GLORYBELLE. "
                    "La richiesta è stata ricevuta."
                )
            },
            status=status.HTTP_201_CREATED,
        )
