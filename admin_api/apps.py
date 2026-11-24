from django.apps import AppConfig


class AdminApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "admin_api"

    def ready(self):
        import admin_api.schema  # noqa: F401
        import admin_api.signals  # noqa: F401
        self._install_otp_admin_site()

    @staticmethod
    def _install_otp_admin_site():
        from django.contrib import admin
        from django.contrib.admin import sites
        from .admin_site import OTPUnfoldAdminSite

        existing_site = admin.site
        secure_site = OTPUnfoldAdminSite(name=existing_site.name)
        secure_site.site_header = existing_site.site_header
        secure_site.site_title = existing_site.site_title
        secure_site.index_title = existing_site.index_title
        for model, model_admin in existing_site._registry.items():
            secure_site.register(model, type(model_admin))
        admin.site = secure_site
        sites.site = secure_site
