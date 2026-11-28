from core.throttling import ClientIPRateThrottle


class EnquiryCreateRateThrottle(ClientIPRateThrottle):
    scope = "enquiry_create"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
