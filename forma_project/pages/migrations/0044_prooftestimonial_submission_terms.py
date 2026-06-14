from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0043_city_primary_areas'),
    ]

    operations = [
        migrations.AddField(
            model_name='prooftestimonial',
            name='forma_marketing_consent',
            field=models.BooleanField(
                default=False,
                help_text='Client opted in to Forma using this video in our own marketing.',
            ),
        ),
        migrations.AddField(
            model_name='prooftestimonial',
            name='video_submission_terms_accepted_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When the client accepted the Video Submission Terms.',
                null=True,
            ),
        ),
    ]
