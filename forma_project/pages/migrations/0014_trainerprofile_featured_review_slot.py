from django.db import migrations, models
import django.core.validators


def set_default_featured_slot(apps, schema_editor):
    TrainerProfile = apps.get_model('pages', 'TrainerProfile')
    for p in TrainerProfile.objects.iterator():
        if p.featured_review_slot is not None:
            continue
        rows = p.client_reviews or []
        if not rows:
            continue
        has = False
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = (item.get('name') or '').strip()
            quote = (item.get('quote') or '').strip()
            rating = item.get('rating')
            ok_rating = isinstance(rating, int) and 1 <= rating <= 5
            if name and quote and ok_rating and bool(item.get('confirmed')):
                has = True
                break
        if has:
            p.featured_review_slot = 0
            p.save(update_fields=['featured_review_slot'])


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0013_trainerprofile_who_i_work_with'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainerprofile',
            name='featured_review_slot',
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text='Which review slot (0–2) is shown as the large standout quote; null = none.',
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(2),
                ],
            ),
        ),
        migrations.RunPython(set_default_featured_slot, migrations.RunPython.noop),
    ]
