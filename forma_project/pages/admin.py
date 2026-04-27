from django.contrib import admin
from django.db.models import (
    Avg,
    Case,
    CharField,
    Count,
    FloatField,
    IntegerField,
    OuterRef,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Concat, Lower

from .profile_analytics import profile_path_for_object

from .models import (
    HttpErrorLog,
    PostcodeDistrict,
    PrimaryArea,
    ProfileEnquiry,
    ProfilePageView,
    ProfileScrollEvent,
    SpecialismCatalog,
    TrainerAdditionalQualification,
    TrainerGalleryPhoto,
    TrainerPriceTier,
    TrainerGym,
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


@admin.register(SpecialismCatalog)
class SpecialismCatalogAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'sort_order', 'is_active', 'created_at')
    list_editable = ('sort_order', 'is_active')
    search_fields = ('title', 'slug')
    ordering = ('title',)


class TrainerSpecialismInline(admin.TabularInline):
    model = TrainerSpecialism
    extra = 0
    fields = ('order', 'catalog', 'title', 'description')
    autocomplete_fields = ('catalog',)


class TrainerPriceTierInline(admin.TabularInline):
    model = TrainerPriceTier
    extra = 0
    fields = ('order', 'label', 'unit_note', 'price', 'is_most_popular')


class TrainerGymInline(admin.TabularInline):
    model = TrainerGym
    extra = 0
    max_num = 5
    fields = ('order', 'name', 'location_area')
    autocomplete_fields = ('location_area',)


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
        'admin_analytics_views',
        'admin_analytics_avg_scroll',
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
                    'years_experience',
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
        (
            'Public page analytics',
            {
                'description': 'Anonymous tracking on this profile’s public URL (pathname only).',
                'fields': ('readonly_public_page_views', 'readonly_public_avg_scroll_pct'),
            },
        ),
    )
    readonly_fields = (
        'readonly_public_page_views',
        'readonly_public_avg_scroll_pct',
    )
    inlines = (
        TrainerWhoIWorkWithInline,
        TrainerAdditionalQualificationInline,
        TrainerSpecialismInline,
        TrainerGymInline,
        TrainerPriceTierInline,
        TrainerGalleryPhotoInline,
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        path_expr = Case(
            When(
                forma_made=True,
                then=Concat(
                    Value('/'),
                    Lower('slug'),
                    Value('/'),
                    Coalesce(Lower('public_url_key'), Value('')),
                    Value('/'),
                ),
            ),
            default=Concat(Value('/'), Lower('slug'), Value('/')),
            output_field=CharField(max_length=512),
        )
        qs = qs.annotate(_trainer_analytics_path=path_expr)
        pv_sq = (
            ProfilePageView.objects.filter(page=OuterRef('_trainer_analytics_path'))
            .order_by()
            .values('page')
            .annotate(c=Count('pk'))
            .values('c')[:1]
        )
        sc_sq = (
            ProfileScrollEvent.objects.filter(page=OuterRef('_trainer_analytics_path'))
            .order_by()
            .values('page')
            .annotate(a=Avg('depth'))
            .values('a')[:1]
        )
        return qs.annotate(
            admin_analytics_views_count=Coalesce(
                Subquery(pv_sq, output_field=IntegerField()),
                Value(0),
                output_field=IntegerField(),
            ),
            admin_analytics_avg_scroll=Subquery(sc_sq, output_field=FloatField()),
        )

    @admin.display(description='Page views', ordering='admin_analytics_views_count')
    def admin_analytics_views(self, obj):
        return getattr(obj, 'admin_analytics_views_count', 0)

    @admin.display(description='Avg scroll %', ordering='admin_analytics_avg_scroll')
    def admin_analytics_avg_scroll(self, obj):
        v = getattr(obj, 'admin_analytics_avg_scroll', None)
        if v is None:
            return '—'
        return f'{float(v):.1f}%'

    @admin.display(description='Page views')
    def readonly_public_page_views(self, obj):
        if obj is None or obj.pk is None:
            return '—'
        n = getattr(obj, 'admin_analytics_views_count', None)
        if n is not None:
            return n
        path = profile_path_for_object(obj)
        return ProfilePageView.objects.filter(page=path).count()

    @admin.display(description='Avg scroll %')
    def readonly_public_avg_scroll_pct(self, obj):
        if obj is None or obj.pk is None:
            return '—'
        v = getattr(obj, 'admin_analytics_avg_scroll', None)
        if v is None:
            path = profile_path_for_object(obj)
            row = ProfileScrollEvent.objects.filter(page=path).aggregate(a=Avg('depth'))
            v = row.get('a')
        if v is None:
            return '—'
        return f'{float(v):.1f}%'


@admin.register(ProfileEnquiry)
class ProfileEnquiryAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'name', 'email', 'message_preview')
    list_filter = ('created_at',)
    search_fields = ('name', 'email', 'message')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

    @admin.display(description='Message')
    def message_preview(self, obj):
        text = (obj.message or '').replace('\n', ' ')
        return (text[:100] + '…') if len(text) > 100 else (text or '—')


@admin.register(HttpErrorLog)
class HttpErrorLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'status_code', 'path', 'exception_type', 'message_short', 'user', 'ip')
    list_filter = ('status_code',)
    search_fields = ('path', 'message', 'exception_type', 'details', 'referrer')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = (
        'status_code',
        'path',
        'query_string',
        'method',
        'message',
        'details',
        'exception_type',
        'user',
        'ip',
        'referrer',
        'created_at',
    )

    @admin.display(description='Message')
    def message_short(self, obj):
        text = (obj.message or '').replace('\n', ' ')
        return (text[:120] + '…') if len(text) > 120 else text

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff
