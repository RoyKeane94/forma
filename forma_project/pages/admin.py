from django.contrib import admin

from .models import (
    PostcodeDistrict,
    PrimaryArea,
    TrainerAdditionalQualification,
    TrainerGalleryPhoto,
    TrainerPriceTier,
    TrainerProfile,
    TrainerSpecialism,
    TrainerWhoIWorkWithItem,
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
    fields = ('order', 'title', 'description')


class TrainerPriceTierInline(admin.TabularInline):
    model = TrainerPriceTier
    extra = 0
    fields = ('order', 'label', 'unit_note', 'price', 'is_most_popular')


class TrainerGalleryPhotoInline(admin.TabularInline):
    model = TrainerGalleryPhoto
    extra = 0


class TrainerWhoIWorkWithInline(admin.TabularInline):
    model = TrainerWhoIWorkWithItem
    extra = 0
    fields = ('order', 'title', 'description')


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
        'contact_email',
        'contact_phone',
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
                'fields': ('client_reviews', 'featured_review_slot'),
            },
        ),
        (
            'Pricing & contact',
            {
                'fields': (
                    'contact_email',
                    'contact_phone',
                    'contact_phone_preference',
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
        TrainerWhoIWorkWithInline,
        TrainerAdditionalQualificationInline,
        TrainerSpecialismInline,
        TrainerPriceTierInline,
        TrainerGalleryPhotoInline,
    )
