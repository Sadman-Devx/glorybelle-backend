from django.urls import path

from admin_api.content_views import (
    PublicHeroListView,
    PublicInstagramGridView,
    PublicTestimonialListView,
)

app_name = "site_content"

urlpatterns = [
    path("hero/", PublicHeroListView.as_view(), name="public-hero"),
    path("instagram/", PublicInstagramGridView.as_view(), name="public-instagram"),
    path(
        "testimonials/",
        PublicTestimonialListView.as_view(),
        name="public-testimonials",
    ),
]
