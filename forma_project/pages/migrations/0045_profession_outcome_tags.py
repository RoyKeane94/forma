from django.db import migrations, models


PT_TAGS = [
    ('lost_weight', 'Lost weight'),
    ('built_strength', 'Built strength'),
    ('recovered_from_injury', 'Recovered from injury'),
    ('improved_mental_health', 'Improved mental health'),
    ('ran_first_race', 'Ran first race'),
    ('back_pain_gone', 'Pain gone'),
    ('got_off_medication', 'Got off medication'),
    ('more_energy', 'More energy'),
    ('first_time_in_the_gym', 'First time in the gym'),
    ('trained_through_pregnancy', 'Trained through pregnancy'),
]

PHYSIO_TAGS = [
    ('pain_resolved', 'Pain resolved'),
    ('avoided_surgery', 'Avoided surgery'),
    ('back_in_sport', 'Back in sport'),
    ('physio_recovered_from_injury', 'Recovered from injury'),
    ('improved_mobility', 'Improved mobility'),
    ('post_op_rehab_complete', 'Post-op rehab complete'),
    ('returned_to_work', 'Returned to work'),
    ('running_again', 'Running again'),
    ('reduced_medication', 'Reduced medication'),
    ('living_without_limits', 'Living without limits'),
]

SPORTS_MASSAGE_TAGS = [
    ('tension_gone', 'Tension gone'),
    ('back_in_training', 'Back in training'),
    ('injury_prevented', 'Injury prevented'),
    ('mobility_restored', 'Mobility restored'),
    ('performance_improved', 'Performance improved'),
    ('recovered_faster', 'Recovered faster'),
    ('pain_managed', 'Pain managed'),
    ('postural_issues_resolved', 'Postural issues resolved'),
    ('pre_event_ready', 'Pre-event ready'),
    ('sleep_improved', 'Sleep improved'),
]


def _seed_profession_outcome_tags(apps, schema_editor):
    ProofOutcomeTag = apps.get_model('pages', 'ProofOutcomeTag')
    for profession, tags in (
        ('personal_trainer', PT_TAGS),
        ('physiotherapist', PHYSIO_TAGS),
        ('sports_massage_therapist', SPORTS_MASSAGE_TAGS),
    ):
        for idx, (key, label) in enumerate(tags, start=1):
            ProofOutcomeTag.objects.update_or_create(
                key=key,
                defaults={
                    'label': label,
                    'profession': profession,
                    'sort_order': idx,
                    'is_active': True,
                },
            )


def _reverse(apps, schema_editor):
    ProofOutcomeTag = apps.get_model('pages', 'ProofOutcomeTag')
    ProofOutcomeTag.objects.filter(
        profession__in=('physiotherapist', 'sports_massage_therapist'),
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0044_prooftestimonial_submission_terms'),
    ]

    operations = [
        migrations.AddField(
            model_name='proofoutcometag',
            name='profession',
            field=models.CharField(
                choices=[
                    ('personal_trainer', 'Personal trainer'),
                    ('physiotherapist', 'Physiotherapist'),
                    ('sports_massage_therapist', 'Sports massage therapist'),
                ],
                db_index=True,
                default='personal_trainer',
                help_text='Which practitioner profession sees this tag on the submit form.',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='proofoutcometag',
            name='label',
            field=models.CharField(max_length=120),
        ),
        migrations.AddConstraint(
            model_name='proofoutcometag',
            constraint=models.UniqueConstraint(
                fields=('profession', 'label'),
                name='pages_outcome_tag_profession_label_unique',
            ),
        ),
        migrations.RunPython(_seed_profession_outcome_tags, _reverse),
    ]
