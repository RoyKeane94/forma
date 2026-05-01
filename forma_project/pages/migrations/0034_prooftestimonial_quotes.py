from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0033_proofoutcometag'),
    ]

    operations = [
        migrations.AddField(
            model_name='prooftestimonial',
            name='pull_quote',
            field=models.CharField(
                blank=True,
                help_text='PT-selected pull quote used when presenting the testimonial.',
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name='prooftestimonial',
            name='suggested_quotes',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='AI-suggested short pull-quote candidates.',
            ),
        ),
    ]
