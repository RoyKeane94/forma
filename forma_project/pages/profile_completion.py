"""Outstanding Proof profile items for the account page."""

from django.db import transaction
from django.urls import reverse

from .models import TrainerGym, TrainerSpecialism
from .profile_display import (
    proof_area_labels,
    proof_hero_media_mode,
    proof_primary_gym_label,
    specialism_display_items,
)


def _profile_setup_url(anchor: str = '') -> str:
    base = reverse('pages:proof_profile_setup')
    if anchor:
        return f'{base}#{anchor}'
    return base


PROFILE_CHECKLIST_SECTIONS = (
    ('name', 'Your name'),
    ('profession', 'Your profession'),
    ('media', 'Profile photo or welcome video'),
    ('location', 'Where you train'),
    ('specialisms', 'Specialisms'),
    ('contact', 'Contact details'),
)


def _profile_name_parts(profile) -> tuple[str, str]:
    first = (profile.first_name or '').strip()
    last = (profile.last_name or '').strip()
    user = getattr(profile, 'user', None)
    if not first and user is not None:
        first = (user.first_name or '').strip()
    if not last and user is not None:
        last = (user.last_name or '').strip()
    return first, last


def _trainer_gyms(profile):
    return [
        g for g in profile.gyms.all()
        if (g.name or '').strip() or g.location_area_id
    ]


def _section_complete(profile, key: str, trainer_gyms) -> bool:
    if key == 'name':
        first, last = _profile_name_parts(profile)
        return bool(first and last)
    if key == 'profession':
        return bool((profile.profession or '').strip())
    if key == 'media':
        return proof_hero_media_mode(profile) != 'empty'
    if key == 'location':
        return bool(proof_area_labels(profile) or proof_primary_gym_label(profile))
    if key == 'specialisms':
        return bool(specialism_display_items(profile))
    if key == 'contact':
        return bool((profile.contact_phone or '').strip() or (profile.contact_email or '').strip())
    return False


def profile_checklist_items(profile) -> list[dict]:
    """All Proof profile sections with completion status for the account page."""
    trainer_gyms = _trainer_gyms(profile)
    return [
        {
            'key': key,
            'label': label,
            'complete': _section_complete(profile, key, trainer_gyms),
            'url': _profile_setup_url(key),
        }
        for key, label in PROFILE_CHECKLIST_SECTIONS
    ]


def profile_outstanding_items(profile) -> list[dict]:
    """Return incomplete Proof profile sections."""
    return [item for item in profile_checklist_items(profile) if not item['complete']]


@transaction.atomic
def save_proof_profile_setup(profile, cleaned_data) -> bool:
    """Save profile setup form. Returns True when a new welcome video was uploaded."""
    old_first = (profile.first_name or '').strip()
    old_last = (profile.last_name or '').strip()

    profile.first_name = (cleaned_data.get('first_name') or '').strip()[:150]
    profile.last_name = (cleaned_data.get('last_name') or '').strip()[:150]
    profile.profession = (cleaned_data.get('profession') or '').strip()

    selected_areas = [
        cleaned_data.get('primary_area'),
        cleaned_data.get('area_2'),
        cleaned_data.get('area_3'),
    ]
    unique_areas = []
    seen_area_ids: set[int] = set()
    for area in selected_areas:
        if area is None or area.pk in seen_area_ids:
            continue
        seen_area_ids.add(area.pk)
        unique_areas.append(area)

    profile.primary_area = unique_areas[0] if unique_areas else None
    profile.other_areas = [area.name for area in unique_areas[1:]]
    profile.contact_email = (cleaned_data.get('contact_email') or '').strip()
    profile.contact_phone = (cleaned_data.get('contact_phone') or '').strip()
    profile.free_consultation = bool(cleaned_data.get('free_consultation'))

    portrait = cleaned_data.get('portrait')
    intro_video = cleaned_data.get('intro_video')
    intro_video_uploaded = False
    if portrait is False:
        profile.portrait = None
    elif portrait:
        profile.portrait = portrait
    if intro_video is False:
        profile.intro_video = None
        profile.intro_video_suggested_quotes = []
        profile.intro_video_pull_quote = ''
        profile.intro_video_transcript = ''
        profile.intro_video_quote_generation_status = 'pending'
        profile.intro_video_quote_generation_updated_at = None
    elif intro_video:
        profile.intro_video = intro_video
        intro_video_uploaded = True
        profile.intro_video_suggested_quotes = []
        profile.intro_video_pull_quote = ''
        profile.intro_video_transcript = ''
        profile.intro_video_quote_generation_status = 'pending'
        profile.intro_video_quote_generation_updated_at = None

    mode = cleaned_data.get('hero_media') or 'photo'
    profile.show_intro_video = bool(mode == 'video' and profile.intro_video)

    update_fields = [
        'profession',
        'primary_area',
        'other_areas',
        'contact_email',
        'contact_phone',
        'free_consultation',
        'show_intro_video',
    ]
    if profile.first_name != old_first:
        update_fields.append('first_name')
    if profile.last_name != old_last:
        update_fields.append('last_name')
    if portrait is False or portrait:
        update_fields.append('portrait')
    if intro_video is False or intro_video:
        update_fields.extend(
            [
                'intro_video',
                'intro_video_suggested_quotes',
                'intro_video_pull_quote',
                'intro_video_transcript',
                'intro_video_quote_generation_status',
                'intro_video_quote_generation_updated_at',
            ]
        )
    profile.save(update_fields=list(dict.fromkeys(update_fields)))

    primary_gym = (cleaned_data.get('primary_gym') or '').strip()
    gyms_by_order = {
        gym.order: gym
        for gym in TrainerGym.objects.filter(profile=profile, order__in=(1, 2, 3))
    }
    gyms_to_update: list[TrainerGym] = []
    gyms_to_create: list[TrainerGym] = []
    for order in (1, 2, 3):
        gym = gyms_by_order.get(order)
        if gym is None:
            gym = TrainerGym(profile=profile, order=order, name='')
            gyms_to_create.append(gym)
        if order == 1:
            gym.name = primary_gym
            if not primary_gym:
                gym.location_area_id = None
        else:
            gym.name = ''
            gym.location_area_id = None
        if gym.pk:
            gyms_to_update.append(gym)
    if gyms_to_create:
        TrainerGym.objects.bulk_create(gyms_to_create)
    if gyms_to_update:
        TrainerGym.objects.bulk_update(gyms_to_update, ['name', 'location_area_id'])

    resolved_specialisms = cleaned_data.get('resolved_specialisms') or []
    specs_by_order = {
        spec.order: spec
        for spec in TrainerSpecialism.objects.filter(profile=profile, order__in=(1, 2, 3))
    }
    specs_to_update: list[TrainerSpecialism] = []
    specs_to_create: list[TrainerSpecialism] = []
    for order in range(1, 4):
        spec = specs_by_order.get(order)
        if spec is None:
            spec = TrainerSpecialism(profile=profile, order=order, title='')
            specs_to_create.append(spec)
        item = resolved_specialisms[order - 1] if order - 1 < len(resolved_specialisms) else None
        if not item:
            spec.catalog_id = None
            spec.title = ''
            spec.description = ''
        else:
            catalog = item.get('catalog')
            spec.catalog_id = catalog.pk if catalog else None
            spec.title = (item.get('title') or '')[:120]
        if spec.pk:
            specs_to_update.append(spec)
    if specs_to_create:
        TrainerSpecialism.objects.bulk_create(specs_to_create)
    if specs_to_update:
        TrainerSpecialism.objects.bulk_update(specs_to_update, ['catalog_id', 'title', 'description'])

    user = getattr(profile, 'user', None)
    if user is not None and (
        (user.first_name or '') != profile.first_name
        or (user.last_name or '') != profile.last_name
    ):
        user.first_name = profile.first_name
        user.last_name = profile.last_name
        user.save(update_fields=['first_name', 'last_name'])

    return intro_video_uploaded
