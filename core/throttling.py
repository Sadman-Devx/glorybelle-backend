from rest_framework.throttling import (
    AnonRateThrottle as DRFAnonRateThrottle,
    BaseThrottle,
    ScopedRateThrottle as DRFScopedRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle as DRFUserRateThrottle,
)


def get_client_ip(request):
    return BaseThrottle().get_ident(request)


class ClientIPThrottleMixin:
    def get_ident(self, request):
        return get_client_ip(request)


class AnonRateThrottle(ClientIPThrottleMixin, DRFAnonRateThrottle):
    pass


class UserRateThrottle(ClientIPThrottleMixin, DRFUserRateThrottle):
    pass


class ScopedRateThrottle(ClientIPThrottleMixin, DRFScopedRateThrottle):
    pass


class ClientIPRateThrottle(ClientIPThrottleMixin, SimpleRateThrottle):
    pass
