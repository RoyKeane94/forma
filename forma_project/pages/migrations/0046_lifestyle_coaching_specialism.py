from django.db import migrations
from django.utils.text import slugify

TITLE = 'Lifestyle Coaching'
SORT_ORDER = 90


def _allocate_slug(SpecialismCatalog, title: str) -> str:
    base = (slugify((title or '')[:120]) or 'specialism')[:100]
    slug = base
    n = 2
    while SpecialismCatalog.objects.filter(slug=slug).exists():
        slug = f'{base[:88]}-{n}'
        n += 1
    return slug


def add_lifestyle_coaching(apps, schema_editor):
    SpecialismCatalog = apps.get_model('pages', 'SpecialismCatalog')
    existing = SpecialismCatalog.objects.filter(title__iexact=TITLE).first()
    if existing:
        changed = False
        if not existing.is_active:
            existing.is_active = True
            changed = True
        if existing.sort_order != SORT_ORDER:
            existing.sort_order = SORT_ORDER
            changed = True
        if (existing.title or '').strip() != TITLE:
            existing.title = TITLE
            changed = True
        if changed:
            existing.save()
        return

    SpecialismCatalog.objects.create(
        title=TITLE,
        slug=_allocate_slug(SpecialismCatalog, TITLE),
        sort_order=SORT_ORDER,
        is_active=True,
    )


def remove_lifestyle_coaching(apps, schema_editor):
    SpecialismCatalog = apps.get_model('pages', 'SpecialismCatalog')
    TrainerSpecialism = apps.get_model('pages', 'TrainerSpecialism')
    rows = list(SpecialismCatalog.objects.filter(title__iexact=TITLE))
    for cat in rows:
        TrainerSpecialism.objects.filter(catalog_id=cat.pk).update(catalog_id=None)
        cat.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0045_profession_outcome_tags'),
    ]

    operations = [
        migrations.RunPython(add_lifestyle_coaching, remove_lifestyle_coaching),
    ]
