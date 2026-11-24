from django.db import transaction
from django.db.models import Max
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.site_content.models import (
    HeroImage,
    InstagramGrid,
    InstagramGridImage,
    Testimonial,
)

from .authentication import AdminJWTAuthentication
from .content_serializers import (
    AdminHeroImageSerializer,
    AdminInstagramGridSerializer,
    AdminTestimonialSerializer,
    ContentMediaAssetSerializer,
    InstagramGridUpdateSerializer,
    PublicHeroImageSerializer,
    PublicInstagramGridSerializer,
    PublicTestimonialSerializer,
)
from .media_storage import public_media_url
from .pagination import AdminPagination
from .permissions import IsAdminReaderManagerWriter


class AdminHeroListCreateView(generics.ListCreateAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]
    serializer_class = AdminHeroImageSerializer
    pagination_class = AdminPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["active"]
    search_fields = ["media_asset__alt_text"]
    ordering_fields = ["sort_order", "created_at", "active"]
    ordering = ["sort_order", "pk"]

    def get_queryset(self):
        return HeroImage.objects.select_related("media_asset").all()

    def perform_create(self, serializer):
        if "sort_order" in self.request.data:
            serializer.save()
            return
        last_order = HeroImage.objects.aggregate(value=Max("sort_order"))["value"]
        serializer.save(sort_order=0 if last_order is None else last_order + 1)


class AdminHeroDetailView(generics.RetrieveUpdateDestroyAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]
    serializer_class = AdminHeroImageSerializer

    def get_queryset(self):
        return HeroImage.objects.select_related("media_asset")


class AdminInstagramGridView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]

    @extend_schema(responses=AdminInstagramGridSerializer)
    def get(self, request):
        grid = InstagramGrid.objects.filter(pk=1).first()
        slots = [None] * 7
        if grid:
            for image in grid.images.select_related("media_asset"):
                slots[image.position] = {
                    "media_asset_id": image.media_asset_id,
                    "media": ContentMediaAssetSerializer(image.media_asset).data,
                }
        return Response(
            {
                "link": grid.link if grid else "https://www.instagram.com/",
                "images": slots,
            }
        )

    @extend_schema(
        request=InstagramGridUpdateSerializer,
        responses=AdminInstagramGridSerializer,
    )
    def put(self, request):
        serializer = InstagramGridUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        with transaction.atomic():
            grid, _ = InstagramGrid.objects.get_or_create(pk=1)
            grid.link = values["link"]
            grid.save(update_fields=["link", "updated_at"])
            grid.images.all().delete()
            InstagramGridImage.objects.bulk_create(
                [
                    InstagramGridImage(
                        grid=grid,
                        media_asset_id=asset_id,
                        position=position,
                    )
                    for position, asset_id in enumerate(values["image_asset_ids"])
                    if asset_id is not None
                ]
            )
        return self.get(request)


class AdminTestimonialListCreateView(generics.ListCreateAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]
    serializer_class = AdminTestimonialSerializer
    pagination_class = AdminPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["active"]
    search_fields = ["name", "quote"]
    ordering_fields = ["name", "created_at", "active"]
    ordering = ["-created_at", "-pk"]

    def get_queryset(self):
        return Testimonial.objects.select_related("photo_asset").all()


class AdminTestimonialDetailView(generics.RetrieveUpdateDestroyAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]
    serializer_class = AdminTestimonialSerializer

    def get_queryset(self):
        return Testimonial.objects.select_related("photo_asset")


class PublicHeroListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicHeroImageSerializer
    pagination_class = AdminPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["media_asset__alt_text"]
    ordering_fields = ["sort_order"]
    ordering = ["sort_order", "pk"]

    def get_queryset(self):
        return HeroImage.objects.filter(active=True).select_related("media_asset")


class PublicInstagramGridView(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    @extend_schema(responses=PublicInstagramGridSerializer)
    def get(self, request):
        grid = InstagramGrid.objects.filter(pk=1).first()
        if not grid:
            return Response({"link": "", "images": []})
        images = list(
            grid.images.select_related("media_asset").order_by("position", "pk")
        )
        if len(images) != 7 or [image.position for image in images] != list(range(7)):
            return Response({"link": "", "images": []})
        return Response(
            {
                "link": grid.link,
                "images": [
                    {
                        "image_url": public_media_url(image.media_asset.object_key_800),
                        "alt_text": image.media_asset.alt_text,
                    }
                    for image in images
                ],
            }
        )


class PublicTestimonialListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicTestimonialSerializer
    pagination_class = AdminPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "quote"]
    ordering_fields = ["name", "created_at"]
    ordering = ["-created_at", "-pk"]

    def get_queryset(self):
        return Testimonial.objects.filter(active=True).select_related("photo_asset")
