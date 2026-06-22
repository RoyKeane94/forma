"""Outstanding Proof profile items for the account page."""

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


def save_proof_profile_setup(profile, cleaned_data) -> bool:
    """Save profile setup form. Returns True when a new welcome video was uploaded."""
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

    mode = cleaned_data.get('hero_media') or 'photo'
    if mode == 'video' and profile.intro_video:
        profile.show_intro_video = True
    else:
        profile.show_intro_video = False

    profile.save()

    primary_gym = (cleaned_data.get('primary_gym') or '').strip()
    gym, _ = TrainerGym.objects.get_or_create(profile=profile, order=1, defaults={'name': ''})
    gym.name = primary_gym
    if not primary_gym:
        gym.location_area = None
    gym.save()
    for order in (2, 3):
        extra_gym, _ = TrainerGym.objects.get_or_create(profile=profile, order=order, defaults={'name': ''})
        extra_gym.name = ''
        extra_gym.location_area = None
        extra_gym.save()

    catalog_ids = cleaned_data.get('resolved_specialisms') or []
    for order in range(1, 4):
        spec, _ = TrainerSpecialism.objects.get_or_create(
            profile=profile,
            order=order,
            defaults={'title': ''},
        )
        item = catalog_ids[order - 1] if order - 1 < len(catalog_ids) else None
        if not item:
            spec.catalog = None
            spec.title = ''
            spec.description = ''
            spec.save()
            continue
        spec.catalog = item.get('catalog')
        spec.title = (item.get('title') or '')[:120]
        spec.save()

    user = getattr(profile, 'user', None)
    if user is not None:
        user.first_name = profile.first_name
        user.last_name = profile.last_name
        user.save(update_fields=['first_name', 'last_name'])

    return intro_video_uploaded
