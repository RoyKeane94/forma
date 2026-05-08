from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0003_index_user_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='welcome_email_sent_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Timestamp of the founder welcome email send (set once to avoid duplicates).',
                null=True,
            ),
        ),
    ]
