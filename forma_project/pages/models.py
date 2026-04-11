from django.conf import settings
from django.db import models
from django.utils.text import slugify


def _empty_list():
    return []


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


class TrainerProfile(models.Model):
    """
    PT onboarding / public profile data for one user.
    Scalar fields map to steps 1, 4 (part), 5 (flag), 6 (handle); JSON lists for presets;
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

    # Step 2 — quick presets (checkbox group)
    quick_qualifications = models.JSONField(default=_empty_list, blank=True)

    # Step 4 — logistics
    training_locations = models.JSONField(default=_empty_list, blank=True)
    primary_area = models.CharField(max_length=128, blank=True)
    postcode_district = models.CharField(max_length=16, blank=True)
    other_areas = models.JSONField(default=_empty_list, blank=True)

    # Step 5
    free_consultation = models.BooleanField(default=False)

    # Step 6
    instagram_handle = models.CharField(
        max_length=64,
        blank=True,
        help_text='Without @; stored plain.',
    )

    onboarding_step = models.PositiveSmallIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(
        default=True,
        help_text='When false, the public trainer URL returns 404 for everyone except the owner.',
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        help_text='Public URL segment: firstname-lastname (with numeric suffix if needed).',
    )

    class Meta:
        db_table = 'pages_trainer_profile'

    def __str__(self):
        return f'TrainerProfile({self.user_id})'

    @staticmethod
    def slug_base_from_names(first_name: str, last_name: str) -> str:
        a = slugify((first_name or '').strip())
        b = slugify((last_name or '').strip())
        parts = [p for p in (a, b) if p]
        return '-'.join(parts) if parts else 'trainer'

    def assign_public_slug(self) -> None:
        base = self.slug_base_from_names(self.first_name, self.last_name)
        candidate = base
        n = 2
        while True:
            qs = TrainerProfile.objects.filter(slug=candidate)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if not qs.exists():
                self.slug = candidate
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
            or not self.slug
        ):
            self.assign_public_slug()
            kwargs['update_fields'] = list(dict.fromkeys(list(update_fields) + ['slug']))
        return super().save(*args, **kwargs)


class TrainerAdditionalQualification(models.Model):
    """Step 2 — free-text rows (up to 4)."""

    profile = models.ForeignKey(
        TrainerProfile,
        on_delete=models.CASCADE,
        related_name='additional_qualifications',
    )
    order = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=255, blank=True)
    detail = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'pages_trainer_add_qual'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'order'],
                name='pages_add_qual_unique_order',
            ),
        ]


class TrainerSpecialism(models.Model):
    """Step 3 — up to four short labels."""

    profile = models.ForeignKey(
        TrainerProfile,
        on_delete=models.CASCADE,
        related_name='specialisms',
    )
    order = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = 'pages_trainer_specialism'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'order'],
                name='pages_spec_unique_order',
            ),
        ]


class TrainerPriceTier(models.Model):
    """Step 5 — four pricing rows."""

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


def ensure_onboarding_children(profile: TrainerProfile) -> None:
    """
    Ensure fixed-count child rows exist so formsets can bind predictably.
    Call from a view before rendering onboarding (e.g. after profile creation).
    """
    for order in range(1, 5):
        TrainerAdditionalQualification.objects.get_or_create(
            profile=profile,
            order=order,
            defaults={'name': '', 'detail': ''},
        )
        TrainerSpecialism.objects.get_or_create(
            profile=profile,
            order=order,
            defaults={'title': ''},
        )
        TrainerPriceTier.objects.get_or_create(
            profile=profile,
            order=order,
            defaults={'label': '', 'unit_note': '', 'price': None},
        )
    for slot in range(1, 7):
        TrainerGalleryPhoto.objects.get_or_create(
            profile=profile,
            slot=slot,
            defaults={},
        )
