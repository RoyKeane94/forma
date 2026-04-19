from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0012_trainer_contact_preference_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainerprofile',
            name='who_i_work_with',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Up to four short client-type labels; shown as chips on the public profile.',
            ),
        ),
    ]
