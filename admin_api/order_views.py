from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, F, IntegerField, Sum, Value
from django.db.models.functions import Greatest
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as django_filters
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, generics, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ProductVariant
from apps.orders.models import Order, OrderAdminNote
from apps.payments.models import Payment

from .authentication import AdminJWTAuthentication
from .order_serializers import (
    AdminDashboardSerializer,
    AdminOrderArchiveSerializer,
    AdminOrderActionResponseSerializer,
    AdminOrderAuditEventSerializer,
    AdminOrderCancelSerializer,
    AdminOrderDetailSerializer,
    AdminOrderHistorySerializer,
    AdminOrderListSerializer,
    AdminOrderNoteCreateSerializer,
    AdminOrderNoteSerializer,
    AdminOrderTransitionSerializer,
)
from .order_services import (
    archive_order,
    cancel_order,
    create_order_note,
    transition_order,
)
from .pagination import AdminPagination
from .permissions import IsAdminReaderManagerWriter, IsAdminRole, IsManager


class AdminOrderFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=Order.STATUS_CHOICES)
    created_after = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="lte"
    )
    email = django_filters.CharFilter(field_name="email", lookup_expr="icontains")
    order_number = django_filters.CharFilter(
        field_name="order_number", lookup_expr="icontains"
    )
    total_min = django_filters.NumberFilter(field_name="total", lookup_expr="gte")
    total_max = django_filters.NumberFilter(field_name="total", lookup_expr="lte")
    include_archived = django_filters.BooleanFilter(method="filter_archived")

    class Meta:
        model = Order
        fields = ()

    @staticmethod
    def filter_archived(queryset, name, include_archived):
        if include_archived:
            return queryset
        return queryset.filter(archived_at__isnull=True)


class AdminOrderListView(generics.ListAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminRole]
    serializer_class = AdminOrderListSerializer
    pagination_class = AdminPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = AdminOrderFilter
    search_fields = [
        "order_number",
        "email",
        "shipping_first_name",
        "shipping_last_name",
    ]
    ordering_fields = ["created_at", "order_number", "status", "total"]
    ordering = ["-created_at", "-pk"]

    def get_queryset(self):
        queryset = Order.objects.annotate(item_count=Count("items"))
        if "include_archived" not in self.request.query_params:
            queryset = queryset.filter(archived_at__isnull=True)
        return queryset

    @extend_schema(
        summary="Elenca gli ordini",
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR),
            OpenApiParameter("created_after", OpenApiTypes.DATETIME),
            OpenApiParameter("created_before", OpenApiTypes.DATETIME),
            OpenApiParameter("email", OpenApiTypes.STR),
            OpenApiParameter("order_number", OpenApiTypes.STR),
            OpenApiParameter("total_min", OpenApiTypes.DECIMAL),
            OpenApiParameter("total_max", OpenApiTypes.DECIMAL),
            OpenApiParameter("search", OpenApiTypes.STR),
            OpenApiParameter("ordering", OpenApiTypes.STR),
            OpenApiParameter("include_archived", OpenApiTypes.BOOL),
            OpenApiParameter("page", OpenApiTypes.INT),
            OpenApiParameter("page_size", OpenApiTypes.INT),
        ],
        responses=AdminOrderListSerializer(many=True),
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AdminOrderDetailView(generics.RetrieveAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminRole]
    serializer_class = AdminOrderDetailSerializer
    queryset = (
        Order.objects.select_related("payment")
        .prefetch_related("items", "admin_notes__author")
    )

    @extend_schema(summary="Recupera il dettaglio di un ordine")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AdminOrderTransitionView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsManager]

    @extend_schema(
        summary="Modifica lo stato di un ordine",
        request=AdminOrderTransitionSerializer,
        responses={
            200: AdminOrderDetailSerializer,
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
            409: OpenApiTypes.OBJECT,
        },
    )
    def post(self, request, pk):
        serializer = AdminOrderTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order, _ = transition_order(
            pk,
            request.user,
            serializer.validated_data["status"],
            serializer.validated_data.get("tracking_number"),
        )
        return Response(AdminOrderDetailSerializer(order).data)


class AdminOrderCancelView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsManager]

    @extend_schema(
        summary="Annulla un ordine e rimborsa il pagamento se necessario",
        request=AdminOrderCancelSerializer,
        responses={
            200: AdminOrderActionResponseSerializer,
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
            409: OpenApiTypes.OBJECT,
            502: OpenApiTypes.OBJECT,
        },
    )
    def post(self, request, pk):
        serializer = AdminOrderCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order, audit_event = cancel_order(
            pk,
            request.user,
            serializer.validated_data["reason"],
        )
        return Response(
            {
                "order": AdminOrderDetailSerializer(order).data,
                "audit_event": AdminOrderAuditEventSerializer(audit_event).data,
            }
        )


class AdminOrderArchiveView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsManager]

    @extend_schema(
        summary="Archivia un ordine senza eliminarlo",
        request=AdminOrderArchiveSerializer,
        responses={
            200: AdminOrderActionResponseSerializer,
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
            409: OpenApiTypes.OBJECT,
        },
    )
    def post(self, request, pk):
        serializer = AdminOrderArchiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order, audit_event = archive_order(
            pk,
            request.user,
            serializer.validated_data["reason"],
        )
        return Response(
            {
                "order": AdminOrderDetailSerializer(order).data,
                "audit_event": AdminOrderAuditEventSerializer(audit_event).data,
            }
        )


class AdminOrderNoteListCreateView(GenericAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]
    pagination_class = AdminPagination
    queryset = OrderAdminNote.objects.none()
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = {
        "author_id": ["exact"],
        "created_at": ["gte", "lte"],
    }
    search_fields = ["body", "author__username", "author__email"]
    ordering_fields = ["created_at", "author_id"]
    ordering = ["-created_at", "-pk"]

    @extend_schema(
        summary="Elenca le note interne di un ordine",
        parameters=[
            OpenApiParameter("author_id", OpenApiTypes.INT),
            OpenApiParameter("created_at__gte", OpenApiTypes.DATETIME),
            OpenApiParameter("created_at__lte", OpenApiTypes.DATETIME),
            OpenApiParameter("search", OpenApiTypes.STR),
            OpenApiParameter("ordering", OpenApiTypes.STR),
            OpenApiParameter("page", OpenApiTypes.INT),
            OpenApiParameter("page_size", OpenApiTypes.INT),
        ],
        responses=AdminOrderNoteSerializer(many=True),
    )
    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        notes = self.filter_queryset(
            order.admin_notes.select_related("author").all()
        )
        page = self.paginate_queryset(notes)
        serializer = AdminOrderNoteSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary="Aggiunge una nota interna a un ordine",
        request=AdminOrderNoteCreateSerializer,
        responses={201: AdminOrderNoteSerializer},
    )
    def post(self, request, pk):
        serializer = AdminOrderNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = create_order_note(pk, request.user, serializer.validated_data["body"])
        return Response(
            AdminOrderNoteSerializer(note).data,
            status=status.HTTP_201_CREATED,
        )


class AdminOrderHistoryView(generics.ListAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminRole]
    serializer_class = AdminOrderHistorySerializer
    pagination_class = AdminPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = {
        "history_type": ["exact"],
        "history_user_id": ["exact"],
        "history_date": ["gte", "lte"],
    }
    search_fields = [
        "status",
        "history_change_reason",
        "history_user__email",
    ]
    ordering_fields = ["history_date", "history_type", "status"]
    ordering = ["-history_date", "-history_id"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.history.none()
        get_object_or_404(Order, pk=self.kwargs["pk"])
        return Order.history.filter(id=self.kwargs["pk"]).select_related("history_user")

    @extend_schema(summary="Elenca la cronologia di un ordine")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


def _dashboard_data():
    now = timezone.now()
    paid_orders = Payment.objects.filter(status="succeeded")
    revenue_7_days = paid_orders.filter(
        order__created_at__gte=now - timedelta(days=7),
        order__created_at__lte=now,
    ).aggregate(value=Sum("amount"))["value"]
    revenue_30_days = paid_orders.filter(
        order__created_at__gte=now - timedelta(days=30),
        order__created_at__lte=now,
    ).aggregate(value=Sum("amount"))["value"]

    counts = dict(
        Order.objects.values("status")
        .annotate(count=Count("pk"))
        .values_list("status", "count")
    )
    low_stock = (
        ProductVariant.objects.filter(
            is_active=True,
            product__is_active=True,
            stock_quantity__lte=3,
        )
        .select_related("product")
        .annotate(
            available_stock=Greatest(
                F("stock_quantity") - F("reserved_quantity"),
                Value(0),
                output_field=IntegerField(),
            )
        )
        .order_by("stock_quantity", "product__name", "sku")
        .values(
            "id",
            "sku",
            "product__name",
            "metal",
            "size",
            "stock_quantity",
            "reserved_quantity",
            "available_stock",
        )
    )
    return {
        "today_orders": Order.objects.filter(created_at__date=timezone.localdate()).count(),
        "revenue_last_7_days": revenue_7_days or 0,
        "revenue_last_30_days": revenue_30_days or 0,
        "orders_by_status": [
            {"status": order_status, "count": counts.get(order_status, 0)}
            for order_status, _ in Order.STATUS_CHOICES
        ],
        "low_stock_variants": [
            {
                "id": item["id"],
                "sku": item["sku"],
                "product_name": item["product__name"],
                "metal": item["metal"],
                "size": item["size"],
                "stock_quantity": item["stock_quantity"],
                "reserved_quantity": item["reserved_quantity"],
                "available_stock": item["available_stock"],
            }
            for item in low_stock
        ],
    }


class AdminDashboardView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminRole]

    @extend_schema(
        summary="Recupera i riepiloghi della dashboard",
        responses=AdminDashboardSerializer,
    )
    def get(self, request):
        data = cache.get_or_set(
            "admin:dashboard:v1",
            _dashboard_data,
            timeout=60,
        )
        return Response(AdminDashboardSerializer(data).data)
