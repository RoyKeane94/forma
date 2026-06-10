from django.db import migrations, models

import pages.models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0039_prooftestimonial_quote_generation_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainerprofile',
            name='intro_video_suggested_quotes',
            field=models.JSONField(blank=True, default=pages.models._empty_list, help_text='AI-suggested pull-quote candidates from the welcome video.'),
        ),
        migrations.AddField(
            model_name='trainerprofile',
            name='intro_video_pull_quote',
            field=models.CharField(blank=True, help_text='Pull quote shown on the welcome video caption.', max_length=120),
        ),
        migrations.AddField(
            model_name='trainerprofile',
            name='intro_video_quote_generation_status',
            field=models.CharField(blank=True, default='pending', help_text='Background quote generation state for the welcome video.', max_length=16),
        ),
        migrations.AddField(
            model_name='trainerprofile',
            name='intro_video_quote_generation_updated_at',
            field=models.DateTimeField(blank=True, help_text='Last time welcome-video quote generation status changed.', null=True),
        ),
    ]
