from drf_spectacular.extensions import OpenApiAuthenticationExtension


class AdminJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "admin_api.authentication.AdminJWTAuthentication"
    name = "AdminJWTBearer"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
