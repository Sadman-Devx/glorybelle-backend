from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SiteContentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.site_content"
    verbose_name = _("Contenuti del sito")
