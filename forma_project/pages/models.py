import logging
import secrets
import string
import traceback

from django.conf import settings
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.text import slugify


def _empty_list():
    return []


def _empty_dict():
    return {}


# ── Step 2: quick-add preset keys (stored on TrainerProfile.quick_qualifications JSON) ──
QUICK_QUALIFICATION_CHOICES = [
    ('reps3', 'REPS Level 3'),
    ('reps4', 'REPS Level 4'),
    ('first_aid', 'First Aid'),
    ('insured', 'Insured'),
    ('pn1', 'Precision Nutrition L1'),
    ('pn2', 'Precision Nutrition L2'),
    ('pre_postnatal', 'Pre/Postnatal'),
    ('sports_massage', 'Sports Massage'),
]

# ── Step 4: where you train (stored on TrainerProfile.training_locations JSON) ──
TRAINING_LOCATION_CHOICES = [
    ('gym', 'Gym'),
    ('home', 'Your home'),
    ('outdoor', 'Outdoor'),
    ('online', 'Online'),
]

CONTACT_PHONE_PREFERENCE_CHOICES = [
    ('call', 'Phone call'),
    ('whatsapp', 'WhatsApp'),
    ('text', 'Text message'),
]


class PostcodeDistrict(models.Model):
    """Outward postcode district (e.g. SW12) for logistics."""

    code = models.CharField(max_length=16, unique=True)

    class Meta:
        db_table = 'pages_postcode_district'
        ordering = ['code']

    def __str__(self) -> str:
        return self.code


class PrimaryArea(models.Model):
    """Named coverage area; links to one postcode district."""

    name = models.CharField(max_length=128, unique=True)
    district = models.ForeignKey(
        PostcodeDistrict,
        on_delete=models.PROTECT,
        related_name='primary_areas',
    )

    class Meta:
        db_table = 'pages_primary_area'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class TrainerProfile(models.Model):
    """
    PT onboarding / public profile data for one user.
    Scalar fields map to steps 1, 4 (part), 5 (flag), 6 (gallery, intro video, handle); JSON lists for presets;
    related models for repeaters and gallery.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trainer_profile',
    )

    # Step 1 — About you
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    tagline = models.CharField(
        max_length=80,
        help_text='One line — what you do and for whom.',
    )
    bio = models.TextField(help_text='Longer profile copy.')
    portrait = models.ImageField(upload_to='trainer/portraits/', blank=True, null=True)
    contact_email = models.EmailField(
        max_length=254,
        blank=True,
        help_text='Shown to clients who want to reach you by email.',
    )
    contact_phone = models.CharField(
        max_length=32,
        blank=True,
        help_text='Digits, spaces, and leading + are fine.',
    )
    contact_phone_preference = models.CharField(
        'Preferred contact method',
        max_length=16,
        blank=True,
        choices=CONTACT_PHONE_PREFERENCE_CHOICES,
        help_text='How you prefer clients to use this number (shown on your public page).',
    )

    # Step 2 — quick presets (checkbox group) + optional client-facing lines per key
    quick_qualifications = models.JSONField(default=_empty_list, blank=True)
    quick_qualification_notes = models.JSONField(
        default=_empty_dict,
        blank=True,
        help_text='Maps quick preset keys to short text shown on the public profile.',
    )

    # Step 4 — logistics
    training_locations = models.JSONField(default=_empty_list, blank=True)
    primary_area = models.ForeignKey(
        PrimaryArea,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='trainer_profiles',
    )
    other_areas = models.JSONField(default=_empty_list, blank=True)

    # Step 5
    free_consultation = models.BooleanField(default=False)

    # Step 6
    instagram_handle = models.CharField(
        max_length=64,
        blank=True,
        help_text='Without @; stored plain.',
    )
    intro_video = models.FileField(
        upload_to='trainer/intro/',
        blank=True,
        null=True,
        max_length=255,
        validators=[
            FileExtensionValidator(allowed_extensions=('mp4', 'webm', 'mov', 'm4v')),
        ],
        help_text='Optional short intro clip (e.g. MP4 or WebM).',
    )
    show_intro_video = models.BooleanField(
        default=True,
        help_text=(
            'When on, the intro video block is shown on your public profile. '
            'If there is no clip yet, visitors see a placeholder.'
        ),
    )
    client_reviews = models.JSONField(
        default=_empty_list,
        blank=True,
        help_text='Up to three {name, quote, rating 1–5, confirmed, focus?, slot 0–2} objects from onboarding.',
    )
    featured_review_slot = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(2)],
        help_text='Which review slot (0–2) is shown as the large standout quote; null = none.',
    )

    onboarding_step = models.PositiveSmallIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(
        default=True,
        help_text='When false, the public trainer URL returns 404 for everyone except the owner.',
    )
    slug = models.SlugField(
        max_length=255,
        unique=False,
        help_text='URL first segment (first-last). Unique for self-serve; Forma-made shares base across keys.',
    )
    forma_made = models.BooleanField(
        default=False,
        help_text='Profile created by a Forma superuser; public URL uses /first-last/KEY/.',
    )
    public_url_key = models.CharField(
        max_length=5,
        blank=True,
        null=True,
        help_text='Five random characters for Forma-made public URLs only.',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='trainer_profiles_created',
    )

    class Meta:
        db_table = 'pages_trainer_profile'
        constraints = [
            models.UniqueConstraint(
                fields=('slug',),
                condition=Q(forma_made=False),
                name='pages_trainer_selfserve_slug_uniq',
            ),
            models.UniqueConstraint(
                fields=('slug', 'public_url_key'),
                condition=Q(forma_made=True),
                name='pages_trainer_forma_slug_key_uniq',
            ),
        ]

    def __str__(self):
        return f'TrainerProfile({self.user_id})'

    @property
    def postcode_district(self) -> str:
        if self.primary_area_id:
            return self.primary_area.district.code
        return ''

    def other_areas_display_labels(self) -> list[str]:
        """Human-readable chips for public profile (catalogue names or custom area names only)."""
        out: list[str] = []
        raw = self.other_areas or []
        if not isinstance(raw, list):
            return out
        for x in raw:
            if isinstance(x, dict):
                name = (x.get('name') or '').strip()
                if not name:
                    continue
                out.append(name)
            else:
                s = str(x).strip()
                if s:
                    out.append(s)
        return out

    def get_absolute_url(self) -> str:
        if self.forma_made and self.public_url_key:
            return reverse(
                'pages:trainer_profile_forma',
                kwargs={'profile_slug': self.slug, 'url_key': self.public_url_key},
            )
        return reverse('pages:trainer_profile', kwargs={'profile_slug': self.slug})

    @staticmethod
    def slug_base_from_names(first_name: str, last_name: str) -> str:
        a = slugify((first_name or '').strip())
        b = slugify((last_name or '').strip())
        parts = [p for p in (a, b) if p]
        return '-'.join(parts) if parts else 'trainer'

    def _allocate_forma_url_key(self) -> str:
        alphabet = string.ascii_lowercase + string.digits
        for _ in range(500):
            key = ''.join(secrets.choice(alphabet) for _ in range(5))
            qs = TrainerProfile.objects.filter(
                slug=self.slug,
                public_url_key=key,
                forma_made=True,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if not qs.exists():
                return key
        raise ValueError('Unable to allocate unique URL key for Forma-made profile.')

    def assign_public_slug(self) -> None:
        base = self.slug_base_from_names(self.first_name, self.last_name)
        if self.forma_made:
            self.slug = base
            if not (self.public_url_key and str(self.public_url_key).strip()):
                self.public_url_key = self._allocate_forma_url_key()
            return

        candidate = base
        n = 2
        while True:
            qs = TrainerProfile.objects.filter(slug=candidate, forma_made=False)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if not qs.exists():
                self.slug = candidate
                self.public_url_key = None
                return
            candidate = f'{base}-{n}'
            n += 1

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields is None:
            self.assign_public_slug()
        elif (
            'first_name' in update_fields
            or 'last_name' in update_fields
            or 'slug' in update_fields
            or 'public_url_key' in update_fields
            or not self.slug
        ):
            self.assign_public_slug()
            extras = ['slug']
            if self.forma_made:
                extras.append('public_url_key')
            kwargs['update_fields'] = list(dict.fromkeys(list(update_fields) + extras))
        return super().save(*args, **kwargs)


class TrainerWhoIWorkWithItem(models.Model):
    """Step 1 — client types (title + optional description) for the public profile grid."""

    profile = models.ForeignKey(
        TrainerProfile,
        on_delete=models.CASCADE,
        related_name='who_i_work_with_items',
    )
    order = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=120, blank=True)
    description = models.CharField(
        max_length=600,
        blank=True,
        help_text='Shown under the title on your public page.',
    )

    class Meta:
        db_table = 'pages_trainer_who_i_work_with'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(
                fields=('profile', 'order'),
                name='pages_who_work_unique_order',
            ),
        ]


class TrainerAdditionalQualification(models.Model):
    """Step 2 — free-text rows (up to 10)."""

    profile = models.ForeignKey(
        TrainerProfile,
        on_delete=models.CASCADE,
        related_name='additional_qualifications',
    )
    order = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=255, blank=True)
    detail = models.CharField(max_length=255, blank=True)
    description = models.TextField(
        blank=True,
        help_text='Short client-facing explanation of what this qualification means.',
    )

    class Meta:
        db_table = 'pages_trainer_add_qual'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'order'],
                name='pages_add_qual_unique_order',
            ),
        ]


class SpecialismCatalog(models.Model):
    """Canonical specialism names for onboarding dropdowns and linking trainer rows."""

    title = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=130, unique=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'pages_specialism_catalog'
        ordering = ['title']

    def __str__(self) -> str:
        return self.title

    @classmethod
    def allocate_slug(cls, title: str) -> str:
        base = (slugify((title or '')[:120]) or 'specialism')[:100]
        slug = base
        n = 2
        while cls.objects.filter(slug=slug).exists():
            slug = f'{base[:88]}-{n}'
            n += 1
        return slug

    @classmethod
    def get_or_create_for_title(cls, title: str) -> tuple['SpecialismCatalog', bool]:
        t = (title or '').strip()[:120]
        if not t:
            raise ValueError('title required')
        existing = cls.objects.filter(title__iexact=t).first()
        if existing:
            return existing, False
        return (
            cls.objects.create(
                title=t,
                slug=cls.allocate_slug(t),
                sort_order=0,
                is_active=True,
            ),
            True,
        )


class TrainerSpecialism(models.Model):
    """Step 3 — up to four short labels plus optional client-facing line each."""

    profile = models.ForeignKey(
        TrainerProfile,
        on_delete=models.CASCADE,
        related_name='specialisms',
    )
    order = models.PositiveSmallIntegerField()
    catalog = models.ForeignKey(
        SpecialismCatalog,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        help_text='When set, the public title comes from the catalog entry.',
    )
    title = models.CharField(max_length=120, blank=True)
    description = models.CharField(
        max_length=280,
        blank=True,
        help_text='Optional: one short sentence explaining this specialism for clients.',
    )

    class Meta:
        db_table = 'pages_trainer_specialism'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'order'],
                name='pages_spec_unique_order',
            ),
        ]

    def resolved_title(self) -> str:
        if self.catalog_id:
            return (self.catalog.title or '').strip()
        return (self.title or '').strip()


class TrainerPriceTier(models.Model):
    """Step 5 — up to ten pricing rows (orders 1–10)."""

    profile = models.ForeignKey(
        TrainerProfile,
        on_delete=models.CASCADE,
        related_name='price_tiers',
    )
    order = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=120, blank=True)
    unit_note = models.CharField(
        max_length=120,
        blank=True,
        help_text='e.g. per session',
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_most_popular = models.BooleanField(
        default=False,
        help_text='Highlight this tier on your public profile (only one should be on).',
    )

    class Meta:
        db_table = 'pages_trainer_price_tier'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'order'],
                name='pages_price_unique_order',
            ),
        ]


class TrainerGalleryPhoto(models.Model):
    """Step 6 — six slots."""

    profile = models.ForeignKey(
        TrainerProfile,
        on_delete=models.CASCADE,
        related_name='gallery_photos',
    )
    slot = models.PositiveSmallIntegerField()
    image = models.ImageField(upload_to='trainer/gallery/', blank=True, null=True)

    class Meta:
        db_table = 'pages_trainer_gallery_photo'
        ordering = ['slot']
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'slot'],
                name='pages_gallery_unique_slot',
            ),
        ]


class HttpErrorLog(models.Model):
    """Recorded HTTP errors and unhandled exceptions for staff review (admin)."""

    status_code = models.PositiveSmallIntegerField(db_index=True)
    path = models.CharField(max_length=2048, blank=True, default='')
    query_string = models.CharField(max_length=2048, blank=True, default='')
    method = models.CharField(max_length=16, blank=True, default='')
    message = models.TextField(blank=True, default='')
    details = models.TextField(blank=True, default='')
    exception_type = models.CharField(max_length=255, blank=True, default='')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    ip = models.CharField(max_length=45, blank=True, default='')
    referrer = models.CharField(max_length=2048, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'pages_http_error_log'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.status_code} {self.path[:80]}'


def record_http_error_log(
    request,
    status_code: int,
    *,
    exception: Exception | None = None,
    message: str = '',
    details: str = '',
) -> None:
    """
    Persist an HTTP error for review in Django admin (HttpErrorLog).
    Swallows DB failures so error handlers never crash.
    """
    log = logging.getLogger(__name__)
    try:
        user = None
        u = getattr(request, 'user', None)
        if u is not None and getattr(u, 'is_authenticated', False):
            user = u
        path = (getattr(request, 'path', None) or '')[:2048]
        q = ''
        meta = getattr(request, 'META', None) or {}
        if isinstance(meta, dict):
            q = (meta.get('QUERY_STRING') or '')[:2048]
        method = (getattr(request, 'method', None) or '')[:16]
        ip = (meta.get('REMOTE_ADDR') or '')[:45]
        if not ip:
            xff = (meta.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
            ip = (xff or '')[:45]
        ref = (meta.get('HTTP_REFERER') or '')[:2048]
        exc_type = ''
        exc_message = (message or '').strip()
        detail_body = (details or '').strip()
        if exception is not None:
            exc_type = type(exception).__name__[:255]
            if not exc_message:
                exc_message = str(exception)[:8000]
            if not detail_body:
                detail_body = ''.join(
                    traceback.format_exception(
                        type(exception),
                        exception,
                        exception.__traceback__,
                    )
                )[:50000]
        if not exc_message:
            exc_message = {400: 'Bad request', 403: 'Forbidden', 404: 'Not found', 500: 'Server error'}.get(
                status_code,
                'HTTP error',
            )
        HttpErrorLog.objects.create(
            status_code=status_code,
            path=path,
            query_string=q,
            method=method,
            message=exc_message[:8000],
            details=detail_body[:50000],
            exception_type=exc_type,
            user=user,
            ip=ip,
            referrer=ref,
        )
    except Exception:
        log.exception('HttpErrorLog.record_http_error_log failed')


def ensure_onboarding_children(profile: TrainerProfile) -> None:
    """
    Ensure fixed-count child rows exist so formsets can bind predictably.
    Call from a view before rendering onboarding (e.g. after profile creation).
    """
    for order in range(1, 11):
        TrainerAdditionalQualification.objects.get_or_create(
            profile=profile,
            order=order,
            defaults={'name': '', 'detail': ''},
        )
    # Step 5 pricing formset: up to 10 rows; four empty slots on new profiles.
    for order in range(1, 5):
        TrainerPriceTier.objects.get_or_create(
            profile=profile,
            order=order,
            defaults={'label': '', 'unit_note': '', 'price': None},
        )
    TrainerPriceTier.objects.filter(profile=profile, order__gt=10).delete()
    # Step 1 — who I work with (up to 8); four empty rows on new profiles.
    for order in range(1, 5):
        TrainerWhoIWorkWithItem.objects.get_or_create(
            profile=profile,
            order=order,
            defaults={'title': '', 'description': ''},
        )
    TrainerWhoIWorkWithItem.objects.filter(profile=profile, order__gt=8).delete()
    # Step 3 caps at four specialisms; extra rows break the formset (max_num=4).
    for order in range(1, 5):
        TrainerSpecialism.objects.get_or_create(
            profile=profile,
            order=order,
            defaults={'title': ''},
        )
    TrainerSpecialism.objects.filter(profile=profile, order__gt=4).delete()
    for slot in range(1, 7):
        TrainerGalleryPhoto.objects.get_or_create(
            profile=profile,
            slot=slot,
            defaults={},
        )
