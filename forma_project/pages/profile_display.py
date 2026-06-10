"""Label resolution for public trainer profile (mirrors model/form choice keys)."""

from .models import QUICK_QUALIFICATION_CHOICES, TRAINING_LOCATION_CHOICES

_QUICK = dict(QUICK_QUALIFICATION_CHOICES)
_LOCS = dict(TRAINING_LOCATION_CHOICES)


def quick_qualification_labels(keys):
    return [_QUICK[k] for k in (keys or []) if k in _QUICK]


def quick_qualification_items(profile):
    """Selected quick presets with optional client-facing note per key."""
    keys = profile.quick_qualifications or []
    raw = getattr(profile, 'quick_qualification_notes', None) or {}
    if not isinstance(raw, dict):
        raw = {}
    return [
        {
            'key': k,
            'label': _QUICK[k],
            'note': (raw.get(k) or '').strip(),
        }
        for k in keys
        if k in _QUICK
    ]


def training_location_labels(keys):
    return [_LOCS[k] for k in (keys or []) if k in _LOCS]


def training_location_items(keys):
    """Keys + labels for template (icons per key)."""
    return [{'key': k, 'label': _LOCS[k]} for k in (keys or []) if k in _LOCS]


def non_empty_additional_qualifications(profile):
    rows = []
    for q in profile.additional_qualifications.all():
        name = (q.name or '').strip()
        detail = (q.detail or '').strip()
        description = (q.description or '').strip()
        if name or detail or description:
            rows.append({'name': name, 'detail': detail, 'description': description})
    return rows


def non_empty_specialisms(profile):
    return [
        s.resolved_title()
        for s in profile.specialisms.filter(order__lte=4).select_related('catalog')
        if s.resolved_title()
    ]


def visible_who_i_work_with_items(profile) -> list[dict]:
    """Title + description rows for the public profile (non-empty slots only)."""
    out = []
    for o in profile.who_i_work_with_items.filter(order__lte=8).order_by('order'):
        title = (o.title or '').strip()
        desc = (o.description or '').strip()
        if title:
            out.append({'title': title, 'description': desc})
    return out


def areas_covered_count(profile) -> int:
    """Primary + other service areas for the proof strip."""
    n = 1 if profile.primary_area_id else 0
    raw = profile.other_areas or []
    if not isinstance(raw, list):
        return n
    for x in raw:
        if isinstance(x, dict):
            if (x.get('name') or '').strip():
                n += 1
        elif str(x).strip():
            n += 1
    return n


def specialism_display_items(profile):
    """Titles with optional brief descriptions for public profile / marketing blocks."""
    out = []
    for s in profile.specialisms.filter(order__lte=4).select_related('catalog'):
        title = s.resolved_title()
        if not title:
            continue
        desc = (s.description or '').strip()
        out.append({'title': title, 'description': desc})
    return out


def proof_hero_media_mode(profile) -> str:
    if profile.show_intro_video and profile.intro_video:
        return 'video'
    if profile.portrait:
        return 'photo'
    return 'empty'


def proof_area_labels(profile) -> list[str]:
    """Primary area plus up to two other catalogue areas for the Proof hero."""
    labels: list[str] = []
    seen: set[str] = set()
    if profile.primary_area_id:
        name = (profile.primary_area.name or '').strip()
        if name:
            key = name.casefold()
            seen.add(key)
            labels.append(name)
    for name in profile.other_areas_display_labels():
        if len(labels) >= 3:
            break
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(name)
    if labels:
        return labels
    for gym in sorted(profile.gyms.all(), key=lambda g: (g.order, g.pk)):
        if not gym.location_area_id:
            continue
        name = (gym.location_area.name or '').strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(name)
        if len(labels) >= 3:
            break
    return labels


def proof_primary_gym_label(profile) -> str:
    """Primary gym name from profile setup (order 1)."""
    gyms = sorted(profile.gyms.all(), key=lambda g: (g.order, g.pk))
    for gym in gyms:
        if gym.order != 1:
            continue
        return (gym.name or '').strip()
    return ''


def proof_location_strapline(profile) -> str:
    """Gym and areas in one line, e.g. Rixo, Twickenham & Acton Green."""
    parts: list[str] = []
    seen: set[str] = set()

    gym = proof_primary_gym_label(profile)
    if gym:
        parts.append(gym)
        seen.add(gym.casefold())

    for label in proof_area_labels(profile):
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        parts.append(label)

    if not parts:
        return ''
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f'{parts[0]} & {parts[1]}'
    return ', '.join(parts[:-1]) + f' & {parts[-1]}'


def _join_areas_natural(areas: list[str]) -> str:
    if not areas:
        return ''
    if len(areas) == 1:
        return areas[0]
    if len(areas) == 2:
        return f'{areas[0]} and {areas[1]}'
    return ', '.join(areas[:-1]) + f' and {areas[-1]}'


def proof_location_byline_segments(profile) -> list[dict]:
    """Composed location byline segments for the Proof hero (emphasis flags for template)."""
    gym = proof_primary_gym_label(profile)
    seen = {gym.casefold()} if gym else set()
    areas: list[str] = []
    for label in proof_area_labels(profile):
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        areas.append(label)

    if gym and areas:
        return [
            {'text': 'Personal trainer at ', 'emph': False},
            {'text': gym, 'emph': True},
            {'text': ', working across ', 'emph': False},
            {'text': _join_areas_natural(areas), 'emph': True},
            {'text': '.', 'emph': False},
        ]
    if gym:
        return [
            {'text': 'Personal trainer at ', 'emph': False},
            {'text': gym, 'emph': True},
            {'text': '.', 'emph': False},
        ]
    if areas:
        return [
            {'text': 'Personal trainer working across ', 'emph': False},
            {'text': _join_areas_natural(areas), 'emph': True},
            {'text': '.', 'emph': False},
        ]
    return []


def proof_specialism_titles(profile) -> list[str]:
    return [item['title'] for item in specialism_display_items(profile)]


def proof_intro_video_pull_quote(profile) -> str:
    quote = (getattr(profile, 'intro_video_pull_quote', '') or '').strip()
    if quote:
        return quote
    suggested = getattr(profile, 'intro_video_suggested_quotes', None) or []
    for item in suggested:
        candidate = (str(item or '')).strip()
        if candidate:
            return candidate
    return ''


def proof_trains_in_labels(profile, trainer_gyms) -> list[str]:
    """Legacy combined labels — prefer proof_area_labels + proof_primary_gym_label."""
    areas = proof_area_labels(profile)
    gym = proof_primary_gym_label(profile)
    if areas or gym:
        labels = list(areas)
        if gym:
            labels.append(gym)
        return labels
    labels: list[str] = []
    for gym in trainer_gyms:
        name = (gym.name or '').strip()
        if name:
            labels.append(name)
            continue
        if gym.location_area_id:
            labels.append(gym.location_area.name)
    if labels:
        return labels
    if profile.primary_area_id:
        labels.append(profile.primary_area.name)
    labels.extend(profile.other_areas_display_labels())
    return labels


def proof_location_strap(profile) -> str:
    if profile.primary_area_id:
        district = profile.postcode_district
        if district:
            return f'{profile.primary_area.name}, {district}'
        return profile.primary_area.name
    labels = profile.other_areas_display_labels()
    if labels:
        return labels[0]
    return ''


def proof_contact_phone(profile) -> str:
    return (profile.contact_phone or '').strip()


def proof_contact_email(profile) -> str:
    return (profile.contact_email or profile.user.email or '').strip()


def visible_price_tiers(profile):
    out = []
    for t in profile.price_tiers.filter(order__lte=10):
        label = (t.label or '').strip()
        has_price = t.price is not None
        if label or has_price:
            out.append(t)
    return out


def non_empty_client_reviews(profile):
    """Structured reviews from onboarding; requires rating + confirmation. Each row has a non-negative slot index."""
    out = []
    legacy_pos = 0
    for item in profile.client_reviews or []:
        if not isinstance(item, dict):
            continue
        name = (item.get('name') or '').strip()
        quote = (item.get('quote') or '').strip()
        rating = item.get('rating')
        if not isinstance(rating, int) or not (1 <= rating <= 5):
            rating = None
        confirmed = bool(item.get('confirmed'))
        if name and quote and rating is not None and confirmed:
            focus = (item.get('focus') or '').strip()
            raw_slot = item.get('slot')
            if isinstance(raw_slot, int) and raw_slot >= 0:
                slot = raw_slot
            else:
                slot = legacy_pos
                legacy_pos += 1
            row = {'name': name, 'quote': quote, 'rating': rating, 'slot': slot}
            if focus:
                row['focus'] = focus
            out.append(row)
    return out


def split_featured_client_reviews(profile, review_rows):
    """
    Pick the standout review from profile.featured_review_slot (index into the saved list), or
    no standout if null. Returns (featured_dict | None, list of rows for the “What clients say”
    grid). The featured review is still included in that list so it appears both in the hero
    block and below.
    """
    if not review_rows:
        return None, []
    slot = getattr(profile, 'featured_review_slot', None)
    if slot is None:
        return None, list(review_rows)
    featured = None
    for r in review_rows:
        if r.get('slot') == slot:
            featured = r
            break
    if featured is None:
        return None, list(review_rows)
    return featured, list(review_rows)


def media_storage_preconnect_origin() -> str:
    """
    HTTPS media host from MEDIA_URL for <link rel="preconnect"> (e.g. S3).
    Empty when media is same-origin (e.g. /media/).
    """
    from django.conf import settings
    from urllib.parse import urlparse

    url = (getattr(settings, 'MEDIA_URL', '') or '').strip()
    if not url.startswith(('http://', 'https://')):
        return ''
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f'{parsed.scheme}://{parsed.netloc}'
    return ''
