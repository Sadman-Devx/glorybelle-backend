from urllib.parse import quote

import boto3
from botocore.config import Config
from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException


class MediaStorageUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Il servizio di archiviazione media non è configurato."
    default_code = "media_storage_unavailable"


class MediaStorageError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Il servizio di archiviazione media non è disponibile."
    default_code = "media_storage_error"


def get_s3_client():
    if not settings.ADMIN_MEDIA_S3_BUCKET:
        raise MediaStorageUnavailable(
            "L'archiviazione media amministrativa non è configurata."
        )
    if not settings.ADMIN_MEDIA_PUBLIC_BASE_URL:
        raise MediaStorageUnavailable(
            "L'URL pubblico/CDN dei media amministrativi non è configurato."
        )
    if bool(settings.ADMIN_MEDIA_S3_ACCESS_KEY_ID) != bool(
        settings.ADMIN_MEDIA_S3_SECRET_ACCESS_KEY
    ):
        raise MediaStorageUnavailable(
            "Le credenziali S3 amministrative non sono configurate correttamente."
        )

    client_options = {
        "region_name": settings.ADMIN_MEDIA_S3_REGION,
        "config": Config(
            signature_version="s3v4",
            s3={
                "addressing_style": (
                    "path" if settings.ADMIN_MEDIA_S3_ENDPOINT_URL else "virtual"
                )
            },
        ),
    }
    if settings.ADMIN_MEDIA_S3_ENDPOINT_URL:
        client_options["endpoint_url"] = settings.ADMIN_MEDIA_S3_ENDPOINT_URL
    if settings.ADMIN_MEDIA_S3_ACCESS_KEY_ID:
        client_options["aws_access_key_id"] = settings.ADMIN_MEDIA_S3_ACCESS_KEY_ID
        client_options["aws_secret_access_key"] = (
            settings.ADMIN_MEDIA_S3_SECRET_ACCESS_KEY
        )
    return boto3.client("s3", **client_options)


def get_presign_ttl():
    ttl = settings.ADMIN_MEDIA_PRESIGN_TTL
    if not 60 <= ttl <= 900:
        raise MediaStorageUnavailable(
            "La durata degli URL di caricamento deve essere compresa tra 60 e 900 secondi."
        )
    return ttl


def public_media_url(object_key):
    base_url = settings.ADMIN_MEDIA_PUBLIC_BASE_URL.rstrip("/")
    if not base_url:
        raise MediaStorageUnavailable(
            "L'URL pubblico/CDN dei media amministrativi non è configurato."
        )
    return f"{base_url}/{quote(object_key, safe='/')}"
