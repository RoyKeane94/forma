"""Label resolution for public trainer profile (mirrors model/form choice keys)."""

from .models import QUICK_QUALIFICATION_CHOICES, TRAINING_LOCATION_CHOICES

_QUICK = dict(QUICK_QUALIFICATION_CHOICES)
_LOCS = dict(TRAINING_LOCATION_CHOICES)


def quick_qualification_labels(keys):
    return [_QUICK[k] for k in (keys or []) if k in _QUICK]


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
        if name or detail:
            rows.append({'name': name, 'detail': detail})
    return rows


def non_empty_specialisms(profile):
    return [s.title.strip() for s in profile.specialisms.all() if (s.title or '').strip()]


def visible_price_tiers(profile):
    out = []
    for t in profile.price_tiers.all():
        label = (t.label or '').strip()
        has_price = t.price is not None
        if label or has_price:
            out.append(t)
    return out
