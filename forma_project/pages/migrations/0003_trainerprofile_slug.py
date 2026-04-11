from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    TrainerProfile = apps.get_model('pages', 'TrainerProfile')

    def base_for(first_name: str, last_name: str) -> str:
        a, b = slugify((first_name or '').strip()), slugify((last_name or '').strip())
        parts = [x for x in (a, b) if x]
        return '-'.join(parts) if parts else 'trainer'

    for profile in TrainerProfile.objects.order_by('pk'):
        base = base_for(profile.first_name, profile.last_name)
        candidate = base
        n = 2
        while TrainerProfile.objects.filter(slug=candidate).exclude(pk=profile.pk).exists():
            candidate = f'{base}-{n}'
            n += 1
        profile.slug = candidate
        profile.save(update_fields=['slug'])


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0002_trainerprofile_is_published'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainerprofile',
            name='slug',
            field=models.SlugField(blank=True, max_length=255, null=True),
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='trainerprofile',
            name='slug',
            field=models.SlugField(
                help_text='Public URL segment: firstname-lastname (with numeric suffix if needed).',
                max_length=255,
                unique=True,
                blank=False,
            ),
        ),
    ]
