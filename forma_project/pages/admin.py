from django.contrib import admin

from .models import (
    TrainerAdditionalQualification,
    TrainerGalleryPhoto,
    TrainerPriceTier,
    TrainerProfile,
    TrainerSpecialism,
)


class TrainerAdditionalQualificationInline(admin.TabularInline):
    model = TrainerAdditionalQualification
    extra = 0


class TrainerSpecialismInline(admin.TabularInline):
    model = TrainerSpecialism
    extra = 0


class TrainerPriceTierInline(admin.TabularInline):
    model = TrainerPriceTier
    extra = 0


class TrainerGalleryPhotoInline(admin.TabularInline):
    model = TrainerGalleryPhoto
    extra = 0


@admin.register(TrainerProfile)
class TrainerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'slug', 'first_name', 'last_name', 'onboarding_step', 'completed_at', 'is_published')
    search_fields = ('first_name', 'last_name', 'user__email', 'user__username')
    inlines = (
        TrainerAdditionalQualificationInline,
        TrainerSpecialismInline,
        TrainerPriceTierInline,
        TrainerGalleryPhotoInline,
    )
