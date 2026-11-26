"""
GLORYBELLE — Root conftest.

Re-exports all shared fixtures from tests/conftest.py so they are
available to tests in apps/*/tests.py.
"""
from tests.conftest import *  # noqa: F401, F403


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_cache():
    """
    Throttle counters and cached API responses live in the (in-memory) cache,
    which is shared by every test in the process. Clear it around each test so
    rate limits (login, enquiries, order lookup, ...) never leak between tests.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
