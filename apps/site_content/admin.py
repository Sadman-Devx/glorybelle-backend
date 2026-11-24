from django.contrib import admin

from .models import HeroImage, InstagramGrid, InstagramGridImage, Testimonial


@admin.register(HeroImage)
class HeroImageAdmin(admin.ModelAdmin):
    list_display = ("id", "media_asset", "sort_order", "active", "updated_at")
    list_filter = ("active",)
    ordering = ("sort_order", "pk")


class InstagramGridImageInline(admin.TabularInline):
    model = InstagramGridImage
    extra = 0


@admin.register(InstagramGrid)
class InstagramGridAdmin(admin.ModelAdmin):
    list_display = ("id", "link", "updated_at")
    inlines = (InstagramGridImageInline,)


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "updated_at")
    list_filter = ("active",)
    search_fields = ("name", "quote")
