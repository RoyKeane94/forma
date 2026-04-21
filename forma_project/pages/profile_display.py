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
        s.resolved_title
        for s in profile.specialisms.filter(order__lte=4).select_related('catalog')
        if s.resolved_title
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
        title = s.resolved_title
        if not title:
            continue
        desc = (s.description or '').strip()
        out.append({'title': title, 'description': desc})
    return out


def visible_price_tiers(profile):
    out = []
    for t in profile.price_tiers.filter(order__lte=10):
        label = (t.label or '').strip()
        has_price = t.price is not None
        if label or has_price:
            out.append(t)
    return out


def non_empty_client_reviews(profile):
    """Structured reviews from onboarding (max three); requires rating + confirmation. Each row has slot 0–2."""
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
            if isinstance(raw_slot, int) and 0 <= raw_slot <= 2:
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
    Pick the standout review from profile.featured_review_slot (0–2), or no standout if null.
    Returns (featured_dict | None, list of rows for the “What clients say” grid). The featured
    review is still included in that list so it appears both in the hero block and below.
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
