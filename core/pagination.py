"""
GLORYBELLE — Pagination.

Default page_size=8 matches the shop grid (3 cols × ~3 rows).
"""
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 8
    page_size_query_param = "page_size"
    max_page_size = 100
