from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.enquiries.models import Enquiry, EnquiryNote

from .authentication import AdminJWTAuthentication
from .enquiry_serializers import (
    ASSIGNABLE_USERS,
    AdminEnquiryAssigneeSerializer,
    AdminEnquiryDetailSerializer,
    AdminEnquiryListSerializer,
    AdminEnquiryNoteCreateSerializer,
    AdminEnquiryNoteSerializer,
    AdminEnquiryUpdateSerializer,
)
from .pagination import AdminPagination
from .permissions import IsAdminReaderManagerWriter, IsManager


class AdminEnquiryFilter(django_filters.FilterSet):
    created_after = django_filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
    )

    class Meta:
        model = Enquiry
        fields = ("status", "topic", "atelier_type", "assigned_to")


class AdminEnquiryListView(generics.ListAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]
    serializer_class = AdminEnquiryListSerializer
    pagination_class = AdminPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = AdminEnquiryFilter
    search_fields = ["name", "email", "message"]
    ordering_fields = ["created_at", "updated_at", "name", "status", "topic"]
    ordering = ["-created_at", "-pk"]

    def get_queryset(self):
        return Enquiry.objects.select_related("assigned_to").all()


class AdminEnquiryAssigneeListView(generics.ListAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]
    serializer_class = AdminEnquiryAssigneeSerializer
    pagination_class = AdminPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["is_superuser"]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = ["username", "email", "first_name", "last_name"]
    ordering = ["first_name", "last_name", "pk"]
    queryset = ASSIGNABLE_USERS


class AdminEnquiryDetailView(generics.RetrieveUpdateAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]
    serializer_class = AdminEnquiryDetailSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return (
            Enquiry.objects.select_related("assigned_to")
            .prefetch_related(
                Prefetch(
                    "internal_notes",
                    queryset=EnquiryNote.objects.select_related("author"),
                )
            )
        )

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return AdminEnquiryUpdateSerializer
        return self.serializer_class

    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            response.data = AdminEnquiryDetailSerializer(
                self.get_object(),
                context=self.get_serializer_context(),
            ).data
        return response


class AdminEnquiryNoteCreateView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsManager]
    serializer_class = AdminEnquiryNoteCreateSerializer

    def post(self, request, pk):
        enquiry = get_object_or_404(Enquiry, pk=pk)
        serializer = AdminEnquiryNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = EnquiryNote.objects.create(
            enquiry=enquiry,
            author=request.user,
            body=serializer.validated_data["body"],
        )
        return Response(
            AdminEnquiryNoteSerializer(note).data,
            status=status.HTTP_201_CREATED,
        )
