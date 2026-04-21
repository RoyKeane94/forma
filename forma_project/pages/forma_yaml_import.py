"""
Apply Forma staff YAML (import_templates/profile.example.yaml shape) to a TrainerProfile.
Used after creating the placeholder user + profile + ensure_onboarding_children().
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml
from django.conf import settings
from django.core.exceptions import ValidationError

from .models import (
    QUICK_QUALIFICATION_CHOICES,
    TRAINING_LOCATION_CHOICES,
    CONTACT_PHONE_PREFERENCE_CHOICES,
    PrimaryArea,
    SpecialismCatalog,
    TrainerAdditionalQualification,
    TrainerPriceTier,
    TrainerSpecialism,
    TrainerWhoIWorkWithItem,
)

_QUICK_KEYS = frozenset(k for k, _ in QUICK_QUALIFICATION_CHOICES)
_TRAIN_LOC_KEYS = frozenset(k for k, _ in TRAINING_LOCATION_CHOICES)
_PHONE_PREF = frozenset(k for k, _ in CONTACT_PHONE_PREFERENCE_CHOICES)


def read_profile_example_template() -> str:
    path = Path(settings.BASE_DIR) / 'import_templates' / 'profile.example.yaml'
    if not path.is_file():
        raise FileNotFoundError(f'Missing template file: {path}')
    return path.read_text(encoding='utf-8')


def parse_forma_profile_yaml(text: str) -> dict:
    if not (text or '').strip():
        raise ValidationError('Paste YAML content before submitting.')
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValidationError(f'Invalid YAML: {e}') from e
    if data is None:
        raise ValidationError('YAML parsed to nothing — use a mapping at the root.')
    if not isinstance(data, dict):
        raise ValidationError('YAML root must be a mapping (key/value document).')
    return data


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ('1', 'true', 'yes', 'y', 'on')


def _coerce_decimal(v):
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    try:
        return Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        return None


def apply_forma_profile_yaml(profile: TrainerProfile, data: dict) -> None:
    """Mutate profile and related rows from parsed YAML. Caller wraps in transaction."""
    user_block = data.get('user') or {}
    if not isinstance(user_block, dict):
        user_block = {}
    prof_in = data.get('profile') or {}
    if not isinstance(prof_in, dict):
        raise ValidationError('Missing or invalid "profile" section.')

    first = (prof_in.get('first_name') or '').strip()
    last = (prof_in.get('last_name') or '').strip()
    if not first or not last:
        raise ValidationError('profile.first_name and profile.last_name are required.')

    profile.first_name = first[:150]
    profile.last_name = last[:150]
    profile.tagline = (prof_in.get('tagline') or '')[:80].strip()
    profile.bio = (prof_in.get('bio') or '').strip() or ''
    profile.contact_email = (prof_in.get('contact_email') or '').strip()[:254]
    profile.contact_phone = (prof_in.get('contact_phone') or '').strip()[:32]
    pref = (prof_in.get('contact_phone_preference') or '').strip().lower()
    profile.contact_phone_preference = pref if pref in _PHONE_PREF else ''
    profile.free_consultation = _truthy(prof_in.get('free_consultation'))
    profile.instagram_handle = (prof_in.get('instagram_handle') or '').strip().lstrip('@')[:64]
    profile.show_intro_video = _truthy(prof_in.get('show_intro_video', True))
    profile.is_published = _truthy(prof_in.get('is_published', True))

    raw_tl = prof_in.get('training_locations')
    if raw_tl is None:
        profile.training_locations = []
    elif isinstance(raw_tl, list):
        cleaned = [str(x).strip().lower() for x in raw_tl if str(x).strip()]
        bad = [x for x in cleaned if x not in _TRAIN_LOC_KEYS]
        if bad:
            raise ValidationError(f'Invalid training_locations keys: {", ".join(bad)}')
        profile.training_locations = cleaned
    else:
        raise ValidationError('profile.training_locations must be a list.')

    pa = (prof_in.get('primary_area') or '').strip()
    if pa:
        area = PrimaryArea.objects.filter(name__iexact=pa).first()
        if not area:
            raise ValidationError(f'Unknown primary_area name: {pa!r} (must match catalogue).')
        profile.primary_area = area
    else:
        profile.primary_area = None

    oa = prof_in.get('other_areas')
    if oa is None:
        profile.other_areas = []
    elif isinstance(oa, list):
        built: list = []
        for x in oa:
            if isinstance(x, str) and x.strip():
                built.append(x.strip())
            elif isinstance(x, dict):
                name = (x.get('name') or '').strip()
                outward = (x.get('outward') or '').strip()
                if name:
                    built.append({'name': name, 'outward': outward})
        profile.other_areas = built
    else:
        raise ValidationError('profile.other_areas must be a list.')

    qq = data.get('quick_qualifications')
    if qq is None:
        profile.quick_qualifications = []
    elif isinstance(qq, list):
        keys = [str(x).strip() for x in qq if str(x).strip()]
        bad = [k for k in keys if k not in _QUICK_KEYS]
        if bad:
            raise ValidationError(f'Invalid quick_qualifications keys: {", ".join(bad)}')
        profile.quick_qualifications = keys
    else:
        raise ValidationError('quick_qualifications must be a list.')

    qn = data.get('quick_qualification_notes')
    if qn is None:
        profile.quick_qualification_notes = {}
    elif isinstance(qn, dict):
        out_notes = {}
        for k, v in qn.items():
            ks = str(k).strip()
            if ks in _QUICK_KEYS and (v is not None):
                out_notes[ks] = str(v).strip()[:600]
        profile.quick_qualification_notes = out_notes
    else:
        raise ValidationError('quick_qualification_notes must be a mapping.')

    who = data.get('who_i_work_with')
    if who is None:
        who = []
    if not isinstance(who, list):
        raise ValidationError('who_i_work_with must be a list.')
    if len(who) > 8:
        raise ValidationError('who_i_work_with allows at most 8 rows.')
    for o in range(1, 9):
        w, _ = TrainerWhoIWorkWithItem.objects.get_or_create(
            profile=profile,
            order=o,
            defaults={'title': '', 'description': ''},
        )
        if o - 1 < len(who):
            row = who[o - 1]
            if not isinstance(row, dict):
                raise ValidationError(f'who_i_work_with[{o}] must be a mapping.')
            w.title = (row.get('title') or '').strip()[:120]
            w.description = (row.get('description') or '').strip()[:600]
        else:
            w.title = ''
            w.description = ''
        w.save()

    specs = data.get('specialisms')
    if specs is None:
        specs = []
    if not isinstance(specs, list):
        raise ValidationError('specialisms must be a list.')
    if len(specs) > 4:
        raise ValidationError('specialisms allows at most 4 rows.')
    for o in range(1, 5):
        ts = TrainerSpecialism.objects.filter(profile=profile, order=o).first()
        if not ts:
            ts = TrainerSpecialism.objects.create(profile=profile, order=o, title='')
        if o - 1 < len(specs):
            row = specs[o - 1]
            if not isinstance(row, dict):
                raise ValidationError(f'specialisms[{o}] must be a mapping.')
            title = (row.get('title') or '').strip()[:120]
            if title:
                cat, _ = SpecialismCatalog.get_or_create_for_title(title)
                ts.catalog = cat
                ts.title = ''
            else:
                ts.catalog = None
                ts.title = ''
            ts.description = (row.get('description') or '').strip()[:280]
        else:
            ts.catalog = None
            ts.title = ''
            ts.description = ''
        ts.save()

    addq = data.get('additional_qualifications')
    if addq is None:
        addq = []
    if not isinstance(addq, list):
        raise ValidationError('additional_qualifications must be a list.')
    if len(addq) > 10:
        raise ValidationError('additional_qualifications allows at most 10 rows.')
    for o in range(1, 11):
        row_obj, _ = TrainerAdditionalQualification.objects.get_or_create(
            profile=profile,
            order=o,
            defaults={'name': '', 'detail': '', 'description': ''},
        )
        if o - 1 < len(addq):
            row = addq[o - 1]
            if not isinstance(row, dict):
                raise ValidationError(f'additional_qualifications[{o}] must be a mapping.')
            row_obj.name = (row.get('name') or '').strip()[:255]
            row_obj.detail = (row.get('detail') or '').strip()[:255]
            row_obj.description = (row.get('description') or '').strip()
        else:
            row_obj.name = ''
            row_obj.detail = ''
            row_obj.description = ''
        row_obj.save()

    prices = data.get('price_tiers')
    if prices is None:
        prices = []
    if not isinstance(prices, list):
        raise ValidationError('price_tiers must be a list.')
    if len(prices) > 10:
        raise ValidationError('price_tiers allows at most 10 rows.')
    popular_count = 0
    for o in range(1, 11):
        tier, _ = TrainerPriceTier.objects.get_or_create(
            profile=profile,
            order=o,
            defaults={'label': '', 'unit_note': '', 'price': None, 'is_most_popular': False},
        )
        if o - 1 < len(prices):
            row = prices[o - 1]
            if not isinstance(row, dict):
                raise ValidationError(f'price_tiers[{o}] must be a mapping.')
            tier.label = (row.get('label') or '').strip()[:120]
            tier.unit_note = (row.get('unit_note') or '').strip()[:120]
            tier.price = _coerce_decimal(row.get('price'))
            mp = _truthy(row.get('is_most_popular'))
            tier.is_most_popular = mp
            if mp:
                popular_count += 1
        else:
            tier.label = ''
            tier.unit_note = ''
            tier.price = None
            tier.is_most_popular = False
        tier.save()
    if popular_count > 1:
        raise ValidationError('At most one price_tiers row may have is_most_popular: true.')

    reviews = data.get('client_reviews')
    if reviews is None:
        reviews = []
    if not isinstance(reviews, list):
        raise ValidationError('client_reviews must be a list.')
    if len(reviews) > 3:
        raise ValidationError('client_reviews allows at most 3 rows.')
    clean_reviews: list[dict] = []
    for i, row in enumerate(reviews):
        if not isinstance(row, dict):
            raise ValidationError(f'client_reviews[{i}] must be a mapping.')
        name = (row.get('name') or '').strip()
        quote = (row.get('quote') or '').strip()
        rating = row.get('rating')
        try:
            ri = int(rating)
        except (TypeError, ValueError):
            ri = 0
        if not name or not quote:
            raise ValidationError('Each client_reviews row needs name and quote.')
        if not (1 <= ri <= 5):
            raise ValidationError('Each client_reviews row needs rating 1–5.')
        if not _truthy(row.get('confirmed')):
            raise ValidationError('Each client_reviews row must have confirmed: true to show publicly.')
        out = {'name': name[:120], 'quote': quote[:600], 'rating': ri, 'confirmed': True}
        focus = (row.get('focus') or '').strip()
        if focus:
            out['focus'] = focus[:120]
        if 'slot' in row and row['slot'] is not None:
            try:
                out['slot'] = int(row['slot'])
            except (TypeError, ValueError):
                pass
        clean_reviews.append(out)
    profile.client_reviews = clean_reviews

    slot = data.get('featured_review_slot')
    if slot is None or slot == '':
        profile.featured_review_slot = None
    else:
        try:
            si = int(slot)
        except (TypeError, ValueError):
            si = None
        if si is not None and 0 <= si <= 2:
            profile.featured_review_slot = si
        else:
            profile.featured_review_slot = None

    profile.save()
