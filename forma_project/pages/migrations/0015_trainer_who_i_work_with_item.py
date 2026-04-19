import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


def migrate_who_json_to_rows(apps, schema_editor):
    TrainerProfile = apps.get_model('pages', 'TrainerProfile')
    Item = apps.get_model('pages', 'TrainerWhoIWorkWithItem')
    for profile in TrainerProfile.objects.iterator():
        raw = profile.who_i_work_with
        if raw is None:
            raw = []
        if not isinstance(raw, list):
            continue
        order = 1
        for entry in raw:
            if order > 8:
                break
            title = ''
            desc = ''
            if isinstance(entry, dict):
                title = str(entry.get('title', '') or '').strip()
                desc = str(entry.get('description', '') or '').strip()
            else:
                title = str(entry).strip()
            if title or desc:
                Item.objects.create(
                    profile_id=profile.pk,
                    order=order,
                    title=title[:120],
                    description=desc[:600],
                )
                order += 1


def seed_empty_who_rows(apps, schema_editor):
    TrainerProfile = apps.get_model('pages', 'TrainerProfile')
    Item = apps.get_model('pages', 'TrainerWhoIWorkWithItem')
    for profile in TrainerProfile.objects.iterator():
        if Item.objects.filter(profile_id=profile.pk).exists():
            continue
        for order in range(1, 5):
            Item.objects.create(profile_id=profile.pk, order=order, title='', description='')


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0014_trainerprofile_featured_review_slot'),
    ]

    operations = [
        migrations.CreateModel(
            name='TrainerWhoIWorkWithItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveSmallIntegerField()),
                ('title', models.CharField(blank=True, max_length=120)),
                (
                    'description',
                    models.CharField(
                        blank=True,
                        help_text='Shown under the title on your public page.',
                        max_length=600,
                    ),
                ),
                (
                    'profile',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='who_i_work_with_items',
                        to='pages.trainerprofile',
                    ),
                ),
            ],
            options={
                'db_table': 'pages_trainer_who_i_work_with',
                'ordering': ['order'],
            },
        ),
        migrations.AddConstraint(
            model_name='trainerwhoiworkwithitem',
            constraint=models.UniqueConstraint(
                fields=('profile', 'order'),
                name='pages_who_work_unique_order',
            ),
        ),
        migrations.RunPython(migrate_who_json_to_rows, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='trainerprofile',
            name='who_i_work_with',
        ),
        migrations.RunPython(seed_empty_who_rows, migrations.RunPython.noop),
    ]
