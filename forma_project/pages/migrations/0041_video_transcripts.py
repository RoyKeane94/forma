from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0040_trainerprofile_intro_video_quotes'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainerprofile',
            name='intro_video_transcript',
            field=models.TextField(blank=True, help_text='Full Whisper transcript from the welcome video.'),
        ),
        migrations.AddField(
            model_name='prooftestimonial',
            name='video_transcript',
            field=models.TextField(blank=True, help_text='Full Whisper transcript from the client video.'),
        ),
    ]
