"""
Consolidate SpecialismCatalog to 9 fixed titles and remap all FKs + review focus text.

New canonical (sort order):
  Weight Loss, Muscle Building & Toning, Strength & Conditioning,
  Mobility & Rehabilitation, Nutrition Coaching, Pre & Postnatal Fitness,
  Sports Performance, Combat Sports, Group Personal Training

Mindset Coaching (and previous mindset aliases) is removed: trainer specialism rows
unlinked; review focus cleared when it only matched that theme.
Unmapped catalog titles not in the table below keep trainer data by SET_NULL + title.
"""

from django.db import migrations
from django.utils.text import slugify

# Order = dropdown / admin order (0, 10, 20, …)
NINE = [
    'Weight Loss',
    'Muscle Building & Toning',
    'Strength & Conditioning',
    'Mobility & Rehabilitation',
    'Nutrition Coaching',
    'Pre & Postnatal Fitness',
    'Sports Performance',
    'Combat Sports',
    'Group Personal Training',
]

# Lowercased source title (catalog or free text) -> target in NINE, or None = removed
LEGACY_TO_TARGET: dict[str, str | None] = {
    # New nine (identity)
    'weight loss': 'Weight Loss',
    'muscle building & toning': 'Muscle Building & Toning',
    'strength & conditioning': 'Strength & Conditioning',
    'mobility & rehabilitation': 'Mobility & Rehabilitation',
    'nutrition coaching': 'Nutrition Coaching',
    'pre & postnatal fitness': 'Pre & Postnatal Fitness',
    'sports performance': 'Sports Performance',
    'combat sports': 'Combat Sports',
    'group personal training': 'Group Personal Training',
    # After 0021 and/or common legacy rows → one of the nine
    'fat loss & body composition': 'Weight Loss',
    'fat loss': 'Weight Loss',
    'body confidence & fat loss': 'Weight Loss',
    'body confidence': 'Weight Loss',
    'muscle tone & development': 'Muscle Building & Toning',
    'strength training': 'Strength & Conditioning',
    'strength & mobility': 'Mobility & Rehabilitation',
    'functional training': 'Strength & Conditioning',
    'functional movement': 'Strength & Conditioning',
    'functional strength training': 'Strength & Conditioning',
    'injury prevention & rehabilitation': 'Mobility & Rehabilitation',
    'injury prevention and rehabilitation': 'Mobility & Rehabilitation',
    'injury rehabilitation': 'Mobility & Rehabilitation',
    'cycling': 'Sports Performance',
    'performance cycling': 'Sports Performance',
    'sports training': 'Sports Performance',
    'boxing': 'Combat Sports',
    'boxing training': 'Combat Sports',
    'muay thai': 'Combat Sports',
    # removed as a product category
    'mindset coaching': None,
    'athletic mindset coaching': None,
}

for _v in LEGACY_TO_TARGET.values():
    if _v is not None and _v not in NINE:
        raise ValueError(f'Invalid LEGACY_TO_TARGET value: {_v!r} (must be one of NINE)')


def _allocate_slug(SpecialismCatalog, title: str) -> str:
    base = (slugify((title or '')[:120]) or 'specialism')[:100]
    slug = base
    n = 2
    while SpecialismCatalog.objects.filter(slug=slug).exists():
        slug = f'{base[:88]}-{n}'
        n += 1
    return slug


def _any_to_nine(legacy_to_target) -> dict[str, str | None]:
    """Lowercased string -> final display in NINE, or None = removed; unknowns omitted until merged with NINE keys."""
    out: dict[str, str | None] = {}
    for k, v in legacy_to_target.items():
        out[k] = v
    for t in NINE:
        out[t.lower()] = t
    return out


# Sentinel for "no mapping" — we use a private object
class _Unmapped:
    pass


UNMAPPED = _Unmapped()

def _resolve_for_migration(title: str, any_map: dict[str, str | None]) -> str | None | _Unmapped:
    t = (title or '').strip()
    if not t:
        return UNMAPPED
    k = t.lower()
    if k in any_map:
        v = any_map[k]
        return v  # str or None
    for nine in NINE:
        if k == nine.lower():
            return nine
    return UNMAPPED


def consolidate_specialisms(apps, schema_editor):
    SpecialismCatalog = apps.get_model('pages', 'SpecialismCatalog')
    TrainerSpecialism = apps.get_model('pages', 'TrainerSpecialism')
    TrainerProfile = apps.get_model('pages', 'TrainerProfile')

    any_map = _any_to_nine(LEGACY_TO_TARGET)
    # Review JSON: any known key -> NINE string (or None to drop)
    def focus_map_value(focus: str) -> str | None:
        r = _resolve_for_migration(focus, any_map)
        if r is UNMAPPED:
            return focus  # keep as-is
        if r is None:
            return ''  # removed
        if isinstance(r, str):
            return r
        return focus

    # 1) Mindset: unlink trainer rows, deactivate/delete catalog
    for removed_title in ('mindset coaching', 'athletic mindset coaching'):
        cats = list(SpecialismCatalog.objects.filter(title__iexact=removed_title))
        for cat in cats:
            rid = cat.pk
            TrainerSpecialism.objects.filter(catalog_id=rid).update(
                catalog_id=None,
                title='',
            )
        SpecialismCatalog.objects.filter(pk__in=[c.pk for c in cats]).delete()

    # 2) For each target in NINE, find all catalog rows that should fold into it
    by_target: dict[str, list] = {t: [] for t in NINE}
    orphans_unmapped: list = []

    for cat in SpecialismCatalog.objects.all().order_by('id'):
        t = (cat.title or '').strip()
        r = _resolve_for_migration(t, any_map)
        if r is UNMAPPED:
            orphans_unmapped.append(cat)
        elif r is None:
            # e.g. stray mindset row; treat like removed
            rid = cat.pk
            TrainerSpecialism.objects.filter(catalog_id=rid).update(
                catalog_id=None,
                title='',
            )
            cat.delete()
        else:
            by_target[r].append(cat)

    # 3) Merge per target: one row per NINE, delete/repoint duplicates
    for order_idx, canonical in enumerate(NINE):
        sort_order = order_idx * 10
        candidates = by_target.get(canonical) or []
        if not candidates:
            SpecialismCatalog.objects.create(
                title=canonical,
                slug=_allocate_slug(SpecialismCatalog, canonical),
                sort_order=sort_order,
                is_active=True,
            )
            continue

        primary = min(candidates, key=lambda c: c.id)
        others = [c for c in candidates if c.pk != primary.pk]
        for o in others:
            other_id = o.pk
            TrainerSpecialism.objects.filter(catalog_id=other_id).update(catalog_id=primary.pk)
            o.delete()

        to_save = False
        if (primary.title or '').strip() != canonical:
            primary.title = canonical
            primary.slug = _allocate_slug(SpecialismCatalog, canonical)
            to_save = True
        if primary.sort_order != sort_order:
            primary.sort_order = sort_order
            to_save = True
        if not primary.is_active:
            primary.is_active = True
            to_save = True
        if to_save:
            primary.save()

    # 4) Unmapped catalog: preserve data as free text, then remove catalog row
    for cat in orphans_unmapped:
        title = (cat.title or '').strip()
        for ts in TrainerSpecialism.objects.filter(catalog_id=cat.pk):
            TrainerSpecialism.objects.filter(pk=ts.pk).update(
                catalog_id=None,
                title=title[:120] if title else ts.title,
            )
        cat.delete()

    # 5) Free-text specialisms (no catalog) — map into NINE or clear if removed
    for ts in TrainerSpecialism.objects.filter(catalog__isnull=True).iterator():
        raw = (ts.title or '').strip()
        if not raw:
            continue
        r = _resolve_for_migration(raw, any_map)
        if r is UNMAPPED:
            continue
        if r is None:
            TrainerSpecialism.objects.filter(pk=ts.pk).update(title='')
            continue
        cat = SpecialismCatalog.objects.filter(title__iexact=r).first()
        if not cat:
            continue
        TrainerSpecialism.objects.filter(pk=ts.pk).update(
            catalog_id=cat.pk,
            title='',
        )

    # 6) client_reviews focus strings
    for profile in TrainerProfile.objects.exclude(client_reviews=[]).iterator():
        raw = profile.client_reviews
        if not isinstance(raw, list):
            continue
        changed = False
        new_rows: list = []
        for row in raw:
            if not isinstance(row, dict):
                new_rows.append(row)
                continue
            row = dict(row)
            focus = (row.get('focus') or '').strip()
            if focus:
                mapped = focus_map_value(focus)
                if mapped != focus:
                    row['focus'] = mapped
                    changed = True
            new_rows.append(row)
        if changed:
            profile.client_reviews = new_rows
            profile.save(update_fields=['client_reviews'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0022_profile_enquiry'),
    ]

    operations = [
        migrations.RunPython(consolidate_specialisms, noop_reverse),
    ]
