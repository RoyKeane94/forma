from django.contrib import admin

from .models import (
    PostcodeDistrict,
    PrimaryArea,
    TrainerAdditionalQualification,
    TrainerGalleryPhoto,
    TrainerPriceTier,
    TrainerProfile,
    TrainerSpecialism,
)


@admin.register(PostcodeDistrict)
class PostcodeDistrictAdmin(admin.ModelAdmin):
    list_display = ('code',)
    search_fields = ('code',)


@admin.register(PrimaryArea)
class PrimaryAreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'district')
    list_select_related = ('district',)
    search_fields = ('name', 'district__code')
    autocomplete_fields = ('district',)


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
    list_display = (
        'user',
        'slug',
        'first_name',
        'last_name',
        'primary_area',
        'postcode_district',
        'forma_made',
        'public_url_key',
        'created_by',
        'onboarding_step',
        'completed_at',
        'is_published',
    )
    search_fields = (
        'first_name',
        'last_name',
        'primary_area__name',
        'primary_area__district__code',
        'user__email',
        'user__username',
    )
    fieldsets = (
        (
            'Service area (logistics)',
            {
                'description': 'Primary area sets the outward postcode district; optional extras are stored as names in JSON.',
                'fields': (
                    'primary_area',
                    'training_locations',
                    'other_areas',
                ),
            },
        ),
        (
            'Identity & URL',
            {
                'fields': (
                    'user',
                    'first_name',
                    'last_name',
                    'slug',
                    'public_url_key',
                    'forma_made',
                    'created_by',
                ),
            },
        ),
        (
            'Profile copy & media',
            {
                'fields': (
                    'tagline',
                    'bio',
                    'portrait',
                    'quick_qualifications',
                    'quick_qualification_notes',
                ),
            },
        ),
        (
            'Public intro video',
            {
                'description': (
                    'When “show intro video” is on, the block appears on the public profile; '
                    'without a file, a placeholder is shown.'
                ),
                'fields': ('show_intro_video', 'intro_video'),
            },
        ),
        (
            'Client reviews (onboarding)',
            {
                'fields': ('client_reviews',),
            },
        ),
        (
            'Pricing & contact',
            {
                'fields': (
                    'free_consultation',
                    'instagram_handle',
                ),
            },
        ),
        (
            'Status',
            {
                'fields': (
                    'onboarding_step',
                    'completed_at',
                    'is_published',
                ),
            },
        ),
    )
    inlines = (
        TrainerAdditionalQualificationInline,
        TrainerSpecialismInline,
        TrainerPriceTierInline,
        TrainerGalleryPhotoInline,
    )
