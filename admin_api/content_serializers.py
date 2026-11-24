from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from apps.catalog.models import MediaAsset
from apps.site_content.models import HeroImage, Testimonial
from .media_storage import public_media_url


class ContentMediaAssetSerializer(serializers.ModelSerializer):
    url_400 = serializers.SerializerMethodField()
    url_800 = serializers.SerializerMethodField()
    url_1600 = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = ("id", "url_400", "url_800", "url_1600", "alt_text")
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


class AdminHeroImageSerializer(serializers.ModelSerializer):
    media_asset_id = serializers.PrimaryKeyRelatedField(
        source="media_asset",
        queryset=MediaAsset.objects.all(),
    )
    media = ContentMediaAssetSerializer(source="media_asset", read_only=True)

    class Meta:
        model = HeroImage
        fields = (
            "id",
            "media_asset_id",
            "media",
            "sort_order",
            "active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "media", "created_at", "updated_at")


class PublicHeroImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    alt_text = serializers.CharField(source="media_asset.alt_text", read_only=True)

    class Meta:
        model = HeroImage
        fields = ("id", "image_url", "alt_text", "sort_order")
        read_only_fields = fields

    @extend_schema_field(serializers.URLField())
    def get_image_url(self, hero):
        return public_media_url(hero.media_asset.object_key_1600)


class AdminTestimonialSerializer(serializers.ModelSerializer):
    photo_asset_id = serializers.PrimaryKeyRelatedField(
        source="photo_asset",
        queryset=MediaAsset.objects.all(),
    )
    photo = ContentMediaAssetSerializer(source="photo_asset", read_only=True)

    class Meta:
        model = Testimonial
        fields = (
            "id",
            "name",
            "quote",
            "photo_asset_id",
            "photo",
            "active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "photo", "created_at", "updated_at")


class PublicTestimonialSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Testimonial
        fields = ("id", "name", "quote", "photo_url")
        read_only_fields = fields

    @extend_schema_field(serializers.URLField())
    def get_photo_url(self, testimonial):
        return public_media_url(testimonial.photo_asset.object_key_400)


class AdminInstagramSlotSerializer(serializers.Serializer):
    media_asset_id = serializers.IntegerField()
    media = ContentMediaAssetSerializer()


class AdminInstagramGridSerializer(serializers.Serializer):
    link = serializers.URLField()
    images = serializers.ListField(
        child=AdminInstagramSlotSerializer(allow_null=True),
        min_length=7,
        max_length=7,
    )


class PublicInstagramImageSerializer(serializers.Serializer):
    image_url = serializers.URLField()
    alt_text = serializers.CharField(allow_blank=True)


class PublicInstagramGridSerializer(serializers.Serializer):
    link = serializers.URLField(allow_blank=True)
    images = serializers.ListField(child=PublicInstagramImageSerializer())


class InstagramGridUpdateSerializer(serializers.Serializer):
    link = serializers.URLField(max_length=500)
    image_asset_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1, allow_null=True),
        min_length=7,
        max_length=7,
    )

    def validate_image_asset_ids(self, asset_ids):
        selected_ids = [asset_id for asset_id in asset_ids if asset_id is not None]
        if len(selected_ids) != len(set(selected_ids)):
            raise serializers.ValidationError(
                "Seleziona sette immagini diverse."
            )
        existing_ids = set(
            MediaAsset.objects.filter(pk__in=selected_ids).values_list("pk", flat=True)
        )
        if existing_ids != set(selected_ids):
            raise serializers.ValidationError(
                "Una o più immagini selezionate non esistono."
            )
        return asset_ids
