import hashlib

from rest_framework.throttling import SimpleRateThrottle


class AdminLoginRateThrottle(SimpleRateThrottle):
    scope = "admin_login"

    def get_cache_key(self, request, view):
        data = request.data
        email = data.get("email", "") if isinstance(data, dict) else ""
        if not isinstance(email, str):
            email = ""
        key = f"{self.get_ident(request)}:{email.strip().casefold()[:254]}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}
