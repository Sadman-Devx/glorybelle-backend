import io
import uuid
import warnings
from datetime import timedelta

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters import rest_framework as django_filters
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework import filters, serializers, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_field

from apps.catalog.models import MediaAsset, PendingMediaUpload

from .authentication import AdminJWTAuthentication
from .media_storage import (
    MediaStorageError,
    get_presign_ttl,
    get_s3_client,
    public_media_url,
)
from .pagination import AdminPagination
from .permissions import IsAdminReaderManagerWriter


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
CONTENT_TYPES = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
RENDITION_SIZES = (400, 800, 1600)


class AdminMediaPresignSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=tuple(CONTENT_TYPES))
    size_bytes = serializers.IntegerField(min_value=1, max_value=MAX_UPLOAD_BYTES)


class AdminMediaRegisterSerializer(serializers.Serializer):
    upload_id = serializers.IntegerField(min_value=1)
    alt_text = serializers.CharField(max_length=200, required=False, allow_blank=True)


class AdminMediaAssetSerializer(serializers.ModelSerializer):
    usage_count = serializers.IntegerField(read_only=True)
    url_400 = serializers.SerializerMethodField()
    url_800 = serializers.SerializerMethodField()
    url_1600 = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = (
            "id",
            "url_400",
            "url_800",
            "url_1600",
            "original_size_bytes",
            "width",
            "height",
            "alt_text",
            "usage_count",
            "created_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.URLField())
    def get_url_400(self, asset):
        return public_media_url(asset.object_key_400)

    @extend_schema_field(serializers.URLField())
    def get_url_800(self, asset):
        return public_media_url(asset.object_key_800)

    @extend_schema_field(serializers.URLField())
    def get_url_1600(self, asset):
        return public_media_url(asset.object_key_1600)


class AdminMediaPresignResponseSerializer(serializers.Serializer):
    upload_id = serializers.IntegerField()
    upload_url = serializers.URLField()
    method = serializers.ChoiceField(choices=("PUT",))
    headers = serializers.DictField(child=serializers.CharField())
    expires_in = serializers.IntegerField()


class AdminMediaPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = AdminMediaAssetSerializer(many=True)


class AdminMediaErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class AdminMediaFilter(django_filters.FilterSet):
    usage_count = django_filters.NumberFilter(field_name="usage_count")

    class Meta:
        model = MediaAsset
        fields = ()


def _delete_objects(client, keys):
    if not keys:
        return
    try:
        response = client.delete_objects(
            Bucket=settings.ADMIN_MEDIA_S3_BUCKET,
            Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
        )
    except (BotoCoreError, ClientError) as exc:
        raise MediaStorageError() from exc
    if response.get("Errors"):
        raise MediaStorageError("Impossibile rimuovere alcuni file media.")


def _discard_pending_upload(client, pending):
    _delete_objects(client, [pending.object_key])
    pending.delete()


def _reject_uploaded_file(client, pending, message):
    _discard_pending_upload(client, pending)
    raise ValidationError({"file": message})


def _process_image(data, declared_content_type):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            source = Image.open(io.BytesIO(data))
            actual_format = source.format
            if actual_format != CONTENT_TYPES[declared_content_type]:
                raise ValidationError(
                    {"file": "Il contenuto del file non corrisponde al tipo dichiarato."}
                )
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValidationError({"file": "L'immagine supera la risoluzione consentita."})
            if getattr(source, "n_frames", 1) != 1:
                raise ValidationError({"file": "Le immagini animate non sono supportate."})
            source.verify()

            source = Image.open(io.BytesIO(data))
            source = ImageOps.exif_transpose(source)
            source.load()
    except ValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise ValidationError(
            {"file": "Il file non è un'immagine valida o è danneggiato."}
        ) from exc

    mode = "RGBA" if "A" in source.getbands() else "RGB"
    clean_source = source.convert(mode)
    clean_canvas = Image.new(mode, clean_source.size)
    clean_canvas.paste(clean_source)
    width, height = clean_canvas.size

    variants = {}
    for edge in RENDITION_SIZES:
        rendition = clean_canvas.copy()
        rendition.thumbnail((edge, edge), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        rendition.save(output, format="WEBP", quality=86, method=6)
        variants[edge] = output.getvalue()
    return variants, width, height


class AdminMediaPresignView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]

    @extend_schema(
        request=AdminMediaPresignSerializer,
        responses={201: AdminMediaPresignResponseSerializer},
    )
    def post(self, request):
        serializer = AdminMediaPresignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ttl = get_presign_ttl()
        client = get_s3_client()
        PendingMediaUpload.objects.filter(expires_at__lte=timezone.now()).delete()
        object_key = f"staging/{uuid.uuid4().hex}"
        try:
            upload_url = client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.ADMIN_MEDIA_S3_BUCKET,
                    "Key": object_key,
                    "ContentType": serializer.validated_data["content_type"],
                    "ContentLength": serializer.validated_data["size_bytes"],
                },
                ExpiresIn=ttl,
            )
        except (BotoCoreError, ClientError) as exc:
            raise MediaStorageError() from exc

        pending = PendingMediaUpload.objects.create(
            object_key=object_key,
            content_type=serializer.validated_data["content_type"],
            declared_size_bytes=serializer.validated_data["size_bytes"],
            uploaded_by=request.user,
            expires_at=timezone.now() + timedelta(seconds=ttl),
        )
        return Response(
            {
                "upload_id": pending.pk,
                "upload_url": upload_url,
                "method": "PUT",
                "headers": {
                    "Content-Type": serializer.validated_data["content_type"]
                },
                "expires_in": ttl,
            },
            status=status.HTTP_201_CREATED,
        )


class AdminMediaListRegisterView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]
    pagination_class = AdminPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = AdminMediaFilter
    search_fields = ["alt_text"]
    ordering_fields = ["created_at", "original_size_bytes", "width", "height"]
    ordering = ["-created_at", "-pk"]

    def get_queryset(self):
        return MediaAsset.objects.annotate(
            usage_count=(
                Count("product_images", distinct=True)
                + Count("hero_images", distinct=True)
                + Count("instagram_images", distinct=True)
                + Count("testimonial_photos", distinct=True)
            )
        )

    def filter_queryset(self, queryset):
        for backend in self.filter_backends:
            queryset = backend().filter_queryset(self.request, queryset, self)
        return queryset

    @extend_schema(responses={200: AdminMediaPageSerializer})
    def get(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = AdminMediaAssetSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=AdminMediaRegisterSerializer,
        responses={201: AdminMediaAssetSerializer},
    )
    def post(self, request):
        serializer = AdminMediaRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pending = get_object_or_404(
            PendingMediaUpload,
            pk=serializer.validated_data["upload_id"],
            uploaded_by=request.user,
        )
        client = get_s3_client()
        if pending.expires_at <= timezone.now():
            _discard_pending_upload(client, pending)
            raise ValidationError({"upload_id": "La sessione di caricamento è scaduta."})

        try:
            metadata = client.head_object(
                Bucket=settings.ADMIN_MEDIA_S3_BUCKET,
                Key=pending.object_key,
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise ValidationError(
                    {"upload_id": "Il file non è ancora presente nell'archivio."}
                ) from exc
            raise MediaStorageError() from exc
        except BotoCoreError as exc:
            raise MediaStorageError() from exc

        actual_size = metadata.get("ContentLength", 0)
        if (
            actual_size < 1
            or actual_size > MAX_UPLOAD_BYTES
            or actual_size != pending.declared_size_bytes
        ):
            _reject_uploaded_file(
                client,
                pending,
                "Il file è vuoto, supera 10 MB o non corrisponde alla dimensione dichiarata.",
            )

        try:
            response = client.get_object(
                Bucket=settings.ADMIN_MEDIA_S3_BUCKET,
                Key=pending.object_key,
            )
            body = response["Body"]
            try:
                file_bytes = body.read(MAX_UPLOAD_BYTES + 1)
            finally:
                body.close()
        except (BotoCoreError, ClientError) as exc:
            raise MediaStorageError() from exc
        if len(file_bytes) != actual_size or len(file_bytes) > MAX_UPLOAD_BYTES:
            _reject_uploaded_file(
                client,
                pending,
                "La dimensione effettiva del file non è valida.",
            )

        try:
            variants, width, height = _process_image(file_bytes, pending.content_type)
        except ValidationError:
            _discard_pending_upload(client, pending)
            raise
        media_id = uuid.uuid4().hex
        keys = {
            edge: f"catalog/{media_id}/{edge}.webp" for edge in RENDITION_SIZES
        }
        uploaded_keys = []
        try:
            for edge, data in variants.items():
                client.put_object(
                    Bucket=settings.ADMIN_MEDIA_S3_BUCKET,
                    Key=keys[edge],
                    Body=data,
                    ContentType="image/webp",
                    CacheControl="public, max-age=31536000, immutable",
                )
                uploaded_keys.append(keys[edge])
        except (BotoCoreError, ClientError) as exc:
            _delete_objects(client, uploaded_keys)
            raise MediaStorageError() from exc

        try:
            _discard_pending_upload(client, pending)
        except MediaStorageError:
            _delete_objects(client, uploaded_keys)
            raise

        try:
            with transaction.atomic():
                asset = MediaAsset.objects.create(
                    object_key_400=keys[400],
                    object_key_800=keys[800],
                    object_key_1600=keys[1600],
                    original_size_bytes=actual_size,
                    width=width,
                    height=height,
                    alt_text=serializer.validated_data.get("alt_text", ""),
                    uploaded_by=request.user,
                )
        except IntegrityError as exc:
            _delete_objects(client, uploaded_keys)
            raise APIException(
                "Impossibile registrare il file media. Ripeti il caricamento."
            ) from exc

        asset.usage_count = 0
        return Response(
            AdminMediaAssetSerializer(
                asset,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class AdminMediaDeleteView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminReaderManagerWriter]

    @extend_schema(
        responses={
            204: None,
            409: AdminMediaErrorSerializer,
        }
    )
    def delete(self, request, pk):
        with transaction.atomic():
            asset = get_object_or_404(
                MediaAsset.objects.select_for_update(),
                pk=pk,
            )
            if (
                asset.product_images.exists()
                or asset.hero_images.exists()
                or asset.instagram_images.exists()
                or asset.testimonial_photos.exists()
            ):
                return Response(
                    {"detail": "Rimuovi l'immagine dai prodotti e dai contenuti prima di eliminarla."},
                    status=status.HTTP_409_CONFLICT,
                )
            client = get_s3_client()
            keys = [
                asset.object_key_400,
                asset.object_key_800,
                asset.object_key_1600,
            ]
            _delete_objects(client, keys)
            asset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
