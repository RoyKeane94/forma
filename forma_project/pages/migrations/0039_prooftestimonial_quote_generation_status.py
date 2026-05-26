from django.db import migrations, models


def backfill_quote_generation_status(apps, schema_editor):
    ProofTestimonial = apps.get_model('pages', 'ProofTestimonial')
    qs = ProofTestimonial.objects.exclude(suggested_quotes=[])
    qs.update(
        quote_generation_status='complete',
        quote_generation_updated_at=models.F('submitted_at'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0038_rename_back_pain_outcome_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='prooftestimonial',
            name='quote_generation_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('processing', 'Processing'),
                    ('complete', 'Complete'),
                    ('skipped', 'Skipped'),
                    ('failed', 'Failed'),
                ],
                default='pending',
                help_text='Background quote generation state for this submission.',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='prooftestimonial',
            name='quote_generation_updated_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Last time quote generation status changed.',
                null=True,
            ),
        ),
        migrations.RunPython(backfill_quote_generation_status, migrations.RunPython.noop),
    ]
