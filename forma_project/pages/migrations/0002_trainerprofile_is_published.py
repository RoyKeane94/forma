from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainerprofile',
            name='is_published',
            field=models.BooleanField(
                default=True,
                help_text='When false, the public trainer URL returns 404 for everyone except the owner.',
            ),
        ),
    ]
