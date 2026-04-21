"""
Remap legacy specialism catalog titles to canonical names (condensed list).

Also updates TrainerSpecialism.catalog FKs, clears free-text titles when a
catalog link replaces them, remaps review `focus` strings in client_reviews JSON,
and sets is_active=False on merged-away catalog rows.
"""

from django.db import migrations
from django.db.models import Q
from django.utils.text import slugify


# (canonical_title, legacy titles that should point at that canonical)
# Matching is case-insensitive on title. Each canonical is also matched to itself.
SPECIALISM_CANONICAL_SPECS = [
    (
        'Fat Loss & Body Composition',
        [
            'Fat Loss',
            'Weight Loss',
            'Fat Loss & Body Composition',
            'Body Confidence & Fat Loss',
        ],
    ),
    ('Body Confidence', ['Body confidence', 'Body Confidence']),
    ('Strength & Conditioning', ['Strength training', 'Strength & Conditioning']),
    ('Strength & Mobility', ['Strength & Mobility']),
    (
        'Functional Training',
        ['Functional movement', 'Functional Strength Training'],
    ),
    (
        'Injury Prevention & Rehabilitation',
        [
            'Injury prevention and rehabilitation',
            'Injury Prevention & Rehabilitation',
            'Injury Rehabilitation',
        ],
    ),
    ('Muscle Tone & Development', []),
    ('Sports Performance', []),
    ('Boxing', ['Boxing Training']),
    ('Performance Cycling', []),
    ('Pre & Postnatal Fitness', []),
    ('Nutrition Coaching', []),
    ('Mindset Coaching', ['Athletic Mindset Coaching']),
]


def _allocate_slug(SpecialismCatalog, title: str) -> str:
    base = (slugify((title or '')[:120]) or 'specialism')[:100]
    slug = base
    n = 2
    while SpecialismCatalog.objects.filter(slug=slug).exists():
        slug = f'{base[:88]}-{n}'
        n += 1
    return slug


def _alias_to_canonical_map():
    """Lowercased title -> exact canonical display string."""
    out = {}
    for canonical, aliases in SPECIALISM_CANONICAL_SPECS:
        c = (canonical or '').strip()
        if not c:
            continue
        keys = {c.lower()}
        for a in aliases:
            t = (a or '').strip()
            if t:
                keys.add(t.lower())
        for k in keys:
            if k in out and out[k] != c:
                raise ValueError(f'Duplicate alias key {k!r} for {out[k]!r} vs {c!r}')
            out[k] = c
    return out


def remap_specialism_catalog(apps, schema_editor):
    SpecialismCatalog = apps.get_model('pages', 'SpecialismCatalog')
    TrainerSpecialism = apps.get_model('pages', 'TrainerSpecialism')
    TrainerProfile = apps.get_model('pages', 'TrainerProfile')

    alias_to_canonical = _alias_to_canonical_map()

    for order_idx, (canonical, aliases) in enumerate(SPECIALISM_CANONICAL_SPECS):
        sort_order = order_idx * 10
        titles_to_match = {canonical, *aliases}
        q = Q()
        for t in titles_to_match:
            t = (t or '').strip()
            if t:
                q |= Q(title__iexact=t)
        candidates = list(SpecialismCatalog.objects.filter(q).order_by('id'))
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
        if others:
            other_ids = [c.pk for c in others]
            TrainerSpecialism.objects.filter(catalog_id__in=other_ids).update(
                catalog_id=primary.pk
            )
            SpecialismCatalog.objects.filter(pk__in=other_ids).delete()

        updates = []
        if primary.title != canonical:
            primary.title = canonical
            primary.slug = _allocate_slug(SpecialismCatalog, canonical)
            updates.extend(['title', 'slug'])
        if primary.sort_order != sort_order:
            primary.sort_order = sort_order
            updates.append('sort_order')
        if not primary.is_active:
            primary.is_active = True
            updates.append('is_active')
        if updates:
            primary.save(update_fields=list(dict.fromkeys(updates)))

    # Free-text titles that match a legacy / canonical name
    for ts in TrainerSpecialism.objects.filter(catalog__isnull=True).iterator():
        raw = (ts.title or '').strip()
        if not raw:
            continue
        key = raw.lower()
        if key not in alias_to_canonical:
            continue
        canon = alias_to_canonical[key]
        cat = SpecialismCatalog.objects.filter(title__iexact=canon).first()
        if not cat:
            continue
        TrainerSpecialism.objects.filter(pk=ts.pk).update(
            catalog_id=cat.pk,
            title='',
        )

    # Review focus tags (JSON) — same display strings as specialisms
    for profile in TrainerProfile.objects.exclude(client_reviews=[]).iterator():
        raw = profile.client_reviews
        if not isinstance(raw, list):
            continue
        changed = False
        new_rows = []
        for row in raw:
            if not isinstance(row, dict):
                new_rows.append(row)
                continue
            row = dict(row)
            focus = (row.get('focus') or '').strip()
            if focus:
                k = focus.lower()
                if k in alias_to_canonical:
                    mapped = alias_to_canonical[k]
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
        ('pages', '0020_specialism_catalog'),
    ]

    operations = [
        migrations.RunPython(remap_specialism_catalog, noop_reverse),
    ]
