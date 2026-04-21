import django.db.models.deletion
from django.db import migrations, models
from django.utils.text import slugify


def seed_specialism_catalog_from_rows(apps, schema_editor):
    TrainerSpecialism = apps.get_model('pages', 'TrainerSpecialism')
    SpecialismCatalog = apps.get_model('pages', 'SpecialismCatalog')
    titles = (
        TrainerSpecialism.objects.exclude(title='')
        .values_list('title', flat=True)
        .distinct()
    )
    seen: set[str] = set()
    for raw in titles:
        t = (raw or '').strip()[:120]
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        base = (slugify(t) or 'specialism')[:100]
        slug = base
        n = 2
        while SpecialismCatalog.objects.filter(slug=slug).exists():
            slug = f'{base[:88]}-{n}'
            n += 1
        SpecialismCatalog.objects.create(title=t, slug=slug, sort_order=0, is_active=True)
    for spec in TrainerSpecialism.objects.all():
        title = (spec.title or '').strip()
        if not title:
            continue
        cat = SpecialismCatalog.objects.filter(title__iexact=title).first()
        if cat:
            spec.catalog_id = cat.pk
            spec.save(update_fields=['catalog_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0019_http_error_log'),
    ]

    operations = [
        migrations.CreateModel(
            name='SpecialismCatalog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=120, unique=True)),
                ('slug', models.SlugField(max_length=130, unique=True)),
                ('sort_order', models.PositiveIntegerField(db_index=True, default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'pages_specialism_catalog',
                'ordering': ['sort_order', 'title'],
            },
        ),
        migrations.AddField(
            model_name='trainerspecialism',
            name='catalog',
            field=models.ForeignKey(
                blank=True,
                help_text='When set, the public title comes from the catalog entry.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='pages.specialismcatalog',
            ),
        ),
        migrations.RunPython(seed_specialism_catalog_from_rows, migrations.RunPython.noop),
    ]
