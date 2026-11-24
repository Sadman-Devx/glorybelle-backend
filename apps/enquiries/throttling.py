from rest_framework.throttling import SimpleRateThrottle


class EnquiryCreateRateThrottle(SimpleRateThrottle):
    scope = "enquiry_create"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
