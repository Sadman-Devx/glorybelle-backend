from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import filters, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalog.models import (
    Category,
    MediaAsset,
    Product,
    ProductImage,
    ProductVariant,
)
from apps.orders.models import OrderItem

from .authentication import AdminJWTAuthentication
from .media_storage import public_media_url
from .pagination import AdminPagination
from .permissions import IsAdminReaderManagerWriter


class AdminCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "is_active")
        read_only_fields = fields


class AdminCategoryListView(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]
    serializer_class = AdminCategorySerializer
    pagination_class = AdminPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["is_active"]
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "sort_order"]
    ordering = ["sort_order", "name"]

    def get_queryset(self):
        return Category.objects.all()


class AdminProductVariantSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True)
    price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
    available_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = (
            "id",
            "product_id",
            "metal",
            "size",
            "sku",
            "price_override",
            "price",
            "stock_quantity",
            "reserved_quantity",
            "available_stock",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "product_id",
            "price",
            "reserved_quantity",
            "available_stock",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            "stock_quantity": {"min_value": 0},
            "price_override": {"min_value": 0, "required": False},
        }

    def validate(self, attrs):
        product_id = (
            self.instance.product_id
            if self.instance
            else self.context["view"].kwargs["product_pk"]
        )
        metal = attrs.get("metal", getattr(self.instance, "metal", None))
        size = attrs.get("size", getattr(self.instance, "size", None))
        duplicate = ProductVariant.objects.filter(
            product_id=product_id,
            metal=metal,
            size=size,
        )
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError(
                {"size": "Esiste già una variante con questo metallo e questa misura."}
            )

        stock_quantity = attrs.get(
            "stock_quantity",
            getattr(self.instance, "stock_quantity", 0),
        )
        reserved_quantity = getattr(self.instance, "reserved_quantity", 0)
        if stock_quantity < reserved_quantity:
            raise serializers.ValidationError(
                {
                    "stock_quantity": (
                        "La quantità non può essere inferiore allo stock riservato."
                    )
                }
            )
        return attrs


class AdminProductImageSerializer(serializers.ModelSerializer):
    media_id = serializers.IntegerField(source="media_asset_id", read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = (
            "id",
            "media_id",
            "image",
            "image_alt",
            "alt_text",
            "is_primary",
            "sort_order",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_image(self, image):
        if image.media_asset_id:
            return public_media_url(image.media_asset.object_key_800)
        if image.image:
            url = image.image.url
            request = self.context.get("request")
            return request.build_absolute_uri(url) if request else url
        return None


class AdminProductImagePageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = AdminProductImageSerializer(many=True)


class AdminProductImageUpdateSerializer(serializers.Serializer):
    media_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
    )
    primary_media_id = serializers.IntegerField(allow_null=True)

    def validate(self, attrs):
        media_ids = attrs["media_ids"]
        primary_id = attrs["primary_media_id"]
        if len(media_ids) != len(set(media_ids)):
            raise serializers.ValidationError(
                {"media_ids": "Ogni immagine può comparire una sola volta."}
            )
        if (media_ids and primary_id not in media_ids) or (
            not media_ids and primary_id is not None
        ):
            raise serializers.ValidationError(
                {"primary_media_id": "Seleziona un'immagine presente nella galleria."}
            )
        return attrs


class AdminProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    variants = AdminProductVariantSerializer(many=True, read_only=True)
    images = AdminProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "category",
            "category_name",
            "base_price",
            "metal",
            "gem",
            "purity",
            "is_active",
            "is_featured",
            "variants",
            "images",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "category_name",
            "variants",
            "images",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            "slug": {"required": False, "allow_blank": True},
            "base_price": {"min_value": 0},
        }

    def validate(self, attrs):
        name = attrs.get("name", getattr(self.instance, "name", ""))
        slug = attrs.get("slug")
        if slug == "" or (slug is None and self.instance is None):
            base_slug = slugify(name)[:220] or "prodotto"
            slug = base_slug
            suffix = 2
            while Product.objects.filter(slug=slug).exists():
                suffix_text = f"-{suffix}"
                slug = f"{base_slug[:220 - len(suffix_text)]}{suffix_text}"
                suffix += 1
            attrs["slug"] = slug
        if slug and Product.objects.filter(slug=slug).exclude(
            pk=getattr(self.instance, "pk", None)
        ).exists():
            raise serializers.ValidationError(
                {"slug": "Esiste già un prodotto con questo slug."}
            )
        return attrs


class AdminProductViewSet(viewsets.ModelViewSet):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]
    serializer_class = AdminProductSerializer
    pagination_class = AdminPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = {
        "category": ["exact"],
        "is_active": ["exact"],
        "is_featured": ["exact"],
        "metal": ["exact"],
    }
    search_fields = ["name", "slug", "description"]
    ordering_fields = ["created_at", "updated_at", "name", "base_price"]
    ordering = ["-created_at", "-pk"]

    def get_queryset(self):
        return (
            Product.objects.select_related("category")
            .prefetch_related("variants", "images__media_asset")
        )

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        product = Product.objects.select_for_update().get(pk=self.get_object().pk)
        list(
            ProductVariant.objects.select_for_update()
            .filter(product=product)
            .values_list("pk", flat=True)
        )
        has_orders = OrderItem.objects.filter(variant__product=product).exists()
        if has_orders:
            product.is_active = False
            product.save(update_fields=["is_active", "updated_at"])
            return Response(
                {"id": product.pk, "is_active": False, "deactivated": True},
                status=status.HTTP_200_OK,
            )
        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        methods=["GET"],
        responses={200: AdminProductImagePageSerializer},
    )
    @extend_schema(
        methods=["PUT"],
        request=AdminProductImageUpdateSerializer,
        responses={200: AdminProductImageSerializer(many=True)},
    )
    @action(detail=True, methods=["get", "put"], url_path="images")
    def images(self, request, pk=None):
        product = self.get_object()
        if request.method == "GET":
            images = product.images.select_related("media_asset").all()
            search = request.query_params.get("search")
            if search:
                images = images.filter(alt_text__icontains=search)
            primary_filter = request.query_params.get("is_primary")
            if primary_filter is not None:
                if primary_filter.lower() not in ("true", "false"):
                    raise serializers.ValidationError(
                        {"is_primary": "Usa true o false."}
                    )
                images = images.filter(is_primary=primary_filter.lower() == "true")
            media_id = request.query_params.get("media_id")
            if media_id is not None:
                try:
                    images = images.filter(media_asset_id=int(media_id))
                except ValueError as exc:
                    raise serializers.ValidationError(
                        {"media_id": "Inserisci un ID media valido."}
                    ) from exc
            ordering = request.query_params.get("ordering", "sort_order")
            if ordering not in ("sort_order", "-sort_order", "created_at", "-created_at"):
                raise serializers.ValidationError(
                    {"ordering": "Ordinamento non supportato."}
                )
            images = images.order_by(ordering, "pk")
            page = self.paginate_queryset(images)
            serializer = AdminProductImageSerializer(
                page,
                many=True,
                context=self.get_serializer_context(),
            )
            return self.get_paginated_response(serializer.data)

        payload = AdminProductImageUpdateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        media_ids = payload.validated_data["media_ids"]
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=product.pk)
            assets = {
                asset.pk: asset
                for asset in MediaAsset.objects.select_for_update().filter(
                    pk__in=media_ids
                )
            }
            if len(assets) != len(media_ids):
                raise serializers.ValidationError(
                    {"media_ids": "Una o più immagini non esistono."}
                )
            images = list(
                ProductImage.objects.select_for_update().filter(product=product)
            )
            existing = {
                image.media_asset_id: image
                for image in images
                if image.media_asset_id is not None
            }
            for image in images:
                if image.is_primary:
                    image.is_primary = False
                    image.save(update_fields=["is_primary"])
            for image in images:
                if image.media_asset_id not in media_ids:
                    image.delete()

            gallery = []
            for order, media_id in enumerate(media_ids):
                image = existing.get(media_id)
                if image is None:
                    image = ProductImage(
                        product=product,
                        media_asset=assets[media_id],
                        alt_text=assets[media_id].alt_text,
                    )
                image.sort_order = order
                image.is_primary = False
                image.save()
                gallery.append(image)

            primary_id = payload.validated_data["primary_media_id"]
            if primary_id is not None:
                primary_image = next(
                    image for image in gallery if image.media_asset_id == primary_id
                )
                primary_image.is_primary = True
                primary_image.save(update_fields=["is_primary"])

        return Response(
            AdminProductImageSerializer(
                ProductImage.objects.filter(product=product)
                .select_related("media_asset")
                .order_by("sort_order"),
                many=True,
                context=self.get_serializer_context(),
            ).data
        )


class AdminProductVariantViewSet(viewsets.ModelViewSet):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]
    serializer_class = AdminProductVariantSerializer
    pagination_class = AdminPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = {"metal": ["exact"], "is_active": ["exact"]}
    search_fields = ["sku", "size", "product__name"]
    ordering_fields = ["sku", "metal", "size", "stock_quantity", "price_override"]
    ordering = ["metal", "size", "pk"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ProductVariant.objects.none()
        get_object_or_404(Product, pk=self.kwargs["product_pk"])
        queryset = ProductVariant.objects.filter(
            product_id=self.kwargs["product_pk"]
        ).select_related("product")
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            queryset = queryset.select_for_update()
        return queryset

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def perform_create(self, serializer):
        product = get_object_or_404(Product, pk=self.kwargs["product_pk"])
        serializer.save(product=product)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        variant = self.get_object()
        if variant.order_items.exists():
            variant.is_active = False
            variant.save(update_fields=["is_active", "updated_at"])
            return Response(
                {"id": variant.pk, "is_active": False, "deactivated": True},
                status=status.HTTP_200_OK,
            )
        variant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
