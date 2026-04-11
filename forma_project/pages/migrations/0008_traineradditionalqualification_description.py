from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0007_trainerprofile_client_reviews'),
    ]

    operations = [
        migrations.AddField(
            model_name='traineradditionalqualification',
            name='description',
            field=models.TextField(
                blank=True,
                help_text='Short client-facing explanation of what this qualification means.',
            ),
        ),
    ]
