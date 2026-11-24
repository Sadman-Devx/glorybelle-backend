from django.urls import path
from rest_framework.routers import SimpleRouter

from .catalog_views import (
    AdminCategoryListView,
    AdminProductVariantViewSet,
    AdminProductViewSet,
)
from .media_views import (
    AdminMediaDeleteView,
    AdminMediaListRegisterView,
    AdminMediaPresignView,
)
from .views import (
    AdminAuditListView,
    AdminLoginView,
    AdminLogoutEverywhereView,
    AdminLogoutView,
    AdminMeView,
    AdminMfaVerifyView,
    AdminTokenRefreshView,
)
from .enquiry_views import (
    AdminEnquiryAssigneeListView,
    AdminEnquiryDetailView,
    AdminEnquiryListView,
    AdminEnquiryNoteCreateView,
)
from .order_views import (
    AdminDashboardView,
    AdminOrderArchiveView,
    AdminOrderCancelView,
    AdminOrderDetailView,
    AdminOrderHistoryView,
    AdminOrderListView,
    AdminOrderNoteListCreateView,
    AdminOrderTransitionView,
)
from .content_views import (
    AdminHeroDetailView,
    AdminHeroListCreateView,
    AdminInstagramGridView,
    AdminTestimonialDetailView,
    AdminTestimonialListCreateView,
)
from .staff_views import (
    AdminStaffDeactivateView,
    AdminStaffListCreateView,
    AdminStaffPasswordLinkView,
    AdminStaffRoleAuditListView,
    AdminStaffRoleUpdateView,
)

app_name = "admin_api"

catalog_router = SimpleRouter()
catalog_router.register("products", AdminProductViewSet, basename="admin-products")

urlpatterns = [
    path("login/", AdminLoginView.as_view(), name="login"),
    path("mfa/verify/", AdminMfaVerifyView.as_view(), name="mfa-verify"),
    path("logout/", AdminLogoutView.as_view(), name="logout"),
    path(
        "logout-everywhere/",
        AdminLogoutEverywhereView.as_view(),
        name="logout-everywhere",
    ),
    path("token/refresh/", AdminTokenRefreshView.as_view(), name="token-refresh"),
    path("me/", AdminMeView.as_view(), name="me"),
    path("audit/", AdminAuditListView.as_view(), name="audit"),
    path("content/hero/", AdminHeroListCreateView.as_view(), name="content-hero"),
    path(
        "content/hero/<int:pk>/",
        AdminHeroDetailView.as_view(),
        name="content-hero-detail",
    ),
    path(
        "content/instagram/",
        AdminInstagramGridView.as_view(),
        name="content-instagram",
    ),
    path(
        "content/testimonials/",
        AdminTestimonialListCreateView.as_view(),
        name="content-testimonials",
    ),
    path(
        "content/testimonials/<int:pk>/",
        AdminTestimonialDetailView.as_view(),
        name="content-testimonial-detail",
    ),
    path("staff/", AdminStaffListCreateView.as_view(), name="staff"),
    path(
        "staff/role-audit/",
        AdminStaffRoleAuditListView.as_view(),
        name="staff-role-audit",
    ),
    path(
        "staff/<int:pk>/",
        AdminStaffRoleUpdateView.as_view(),
        name="staff-role",
    ),
    path(
        "staff/<int:pk>/deactivate/",
        AdminStaffDeactivateView.as_view(),
        name="staff-deactivate",
    ),
    path(
        "staff/<int:pk>/password-link/",
        AdminStaffPasswordLinkView.as_view(),
        name="staff-password-link",
    ),
    path("enquiries/", AdminEnquiryListView.as_view(), name="enquiries"),
    path(
        "enquiries/assignees/",
        AdminEnquiryAssigneeListView.as_view(),
        name="enquiry-assignees",
    ),
    path(
        "enquiries/<int:pk>/",
        AdminEnquiryDetailView.as_view(),
        name="enquiry-detail",
    ),
    path(
        "enquiries/<int:pk>/notes/",
        AdminEnquiryNoteCreateView.as_view(),
        name="enquiry-notes",
    ),
    path("dashboard/", AdminDashboardView.as_view(), name="dashboard"),
    path(
        "categories/",
        AdminCategoryListView.as_view({"get": "list"}),
        name="admin-categories",
    ),
    path("orders/", AdminOrderListView.as_view(), name="orders"),
    path("orders/<int:pk>/", AdminOrderDetailView.as_view(), name="order-detail"),
    path(
        "orders/<int:pk>/transition/",
        AdminOrderTransitionView.as_view(),
        name="order-transition",
    ),
    path(
        "orders/<int:pk>/cancel/",
        AdminOrderCancelView.as_view(),
        name="order-cancel",
    ),
    path(
        "orders/<int:pk>/archive/",
        AdminOrderArchiveView.as_view(),
        name="order-archive",
    ),
    path(
        "orders/<int:pk>/notes/",
        AdminOrderNoteListCreateView.as_view(),
        name="order-notes",
    ),
    path(
        "orders/<int:pk>/history/",
        AdminOrderHistoryView.as_view(),
        name="order-history",
    ),
    path("media/presign/", AdminMediaPresignView.as_view(), name="media-presign"),
    path("media/", AdminMediaListRegisterView.as_view(), name="media-list-register"),
    path("media/<int:pk>/", AdminMediaDeleteView.as_view(), name="media-delete"),
    path(
        "products/<int:product_pk>/variants/",
        AdminProductVariantViewSet.as_view({"get": "list", "post": "create"}),
        name="admin-product-variant-list",
    ),
    path(
        "products/<int:product_pk>/variants/<int:pk>/",
        AdminProductVariantViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="admin-product-variant-detail",
    ),
    *catalog_router.urls,
]
