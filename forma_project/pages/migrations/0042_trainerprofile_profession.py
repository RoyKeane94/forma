from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0041_video_transcripts'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainerprofile',
            name='profession',
            field=models.CharField(
                blank=True,
                choices=[
                    ('personal_trainer', 'Personal trainer'),
                    ('physiotherapist', 'Physiotherapist'),
                    ('sports_massage_therapist', 'Sports massage therapist'),
                ],
                help_text='Primary profession shown on the Proof page.',
                max_length=32,
            ),
        ),
    ]
