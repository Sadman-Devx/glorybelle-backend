from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.urls import reverse

from .security import get_active_admin_session


class AdminSessionPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        is_admin_route = path == "/admin" or path.startswith("/admin/")
        is_login = path in ("/admin/login", "/admin/login/")
        user = request.user

        if is_admin_route and not is_login and user.is_authenticated:
            session_id = request.session.get("admin_auth_session_id")
            active_session = (
                get_active_admin_session(user, session_id, touch=True)
                if user.is_superuser and user.is_verified()
                else None
            )
            if active_session is None:
                logout(request)
                return redirect_to_login(
                    request.get_full_path(),
                    login_url=reverse("admin:login"),
                )
            request.session.modified = True

        return self.get_response(request)


class AdminSecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path_info
        if path.startswith("/api/admin/"):
            policy = (
                "default-src 'none'; base-uri 'none'; form-action 'none'; "
                "object-src 'none'; frame-ancestors 'none'"
            )
        elif path == "/admin" or path.startswith("/admin/"):
            policy = (
                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "font-src 'self' data:; object-src 'none'; base-uri 'self'; "
                "form-action 'self'; frame-ancestors 'none'"
            )
        else:
            return response

        response["Content-Security-Policy"] = policy
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "DENY"
        response["Referrer-Policy"] = "same-origin"
        response["Cache-Control"] = "no-store"
        response["X-Robots-Tag"] = "noindex"
        return response
