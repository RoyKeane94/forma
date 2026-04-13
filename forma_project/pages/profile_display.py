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
        s.title.strip()
        for s in profile.specialisms.filter(order__lte=4)
        if (s.title or '').strip()
    ]


def specialism_display_items(profile):
    """Titles with optional brief descriptions for public profile / marketing blocks."""
    out = []
    for s in profile.specialisms.filter(order__lte=4):
        title = (s.title or '').strip()
        if not title:
            continue
        desc = (s.description or '').strip()
        out.append({'title': title, 'description': desc})
    return out


def visible_price_tiers(profile):
    out = []
    for t in profile.price_tiers.filter(order__lte=4):
        label = (t.label or '').strip()
        has_price = t.price is not None
        if label or has_price:
            out.append(t)
    return out


def non_empty_client_reviews(profile):
    """Structured reviews from onboarding (max three); requires rating + confirmation."""
    out = []
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
            row = {'name': name, 'quote': quote, 'rating': rating}
            if focus:
                row['focus'] = focus
            out.append(row)
    return out
