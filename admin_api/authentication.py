from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication

from .security import get_active_admin_session


class AdminJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, token = result
        if token.get("admin_auth") is not True:
            raise PermissionDenied("Accesso all'area amministrativa non consentito.")
        if get_active_admin_session(
            user, token.get("admin_session_id"), touch=True
        ) is None:
            raise PermissionDenied("La sessione amministrativa è scaduta.")
        return user, token
