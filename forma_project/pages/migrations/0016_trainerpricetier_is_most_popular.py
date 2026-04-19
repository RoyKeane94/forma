from django.db import migrations, models


def set_initial_most_popular(apps, schema_editor):
    TrainerPriceTier = apps.get_model('pages', 'TrainerPriceTier')
    profile_ids = (
        TrainerPriceTier.objects.order_by('profile_id')
        .values_list('profile_id', flat=True)
        .distinct()
    )
    for pid in profile_ids:
        tiers = list(
            TrainerPriceTier.objects.filter(profile_id=pid, order__lte=10).order_by('order')
        )
        visible = []
        for t in tiers:
            label = (t.label or '').strip()
            if label or t.price is not None:
                visible.append(t)
        n = len(visible)
        if n == 0:
            continue
        if n == 1:
            idx = 0
        elif n == 2:
            idx = 1
        else:
            idx = n // 2
        chosen = visible[idx]
        chosen.is_most_popular = True
        chosen.save(update_fields=['is_most_popular'])


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0015_trainer_who_i_work_with_item'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainerpricetier',
            name='is_most_popular',
            field=models.BooleanField(
                default=False,
                help_text='Highlight this tier on your public profile (only one should be on).',
            ),
        ),
        migrations.RunPython(set_initial_most_popular, migrations.RunPython.noop),
    ]
