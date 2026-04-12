import pages.models

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0008_traineradditionalqualification_description'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainerprofile',
            name='quick_qualification_notes',
            field=models.JSONField(blank=True, default=pages.models._empty_dict),
        ),
    ]
