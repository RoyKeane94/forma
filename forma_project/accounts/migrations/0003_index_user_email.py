from django.conf import settings
from django.db import migrations, models
from django.db.migrations import RunPython


def _add_email_index(apps, schema_editor):
    if str(getattr(settings, 'AUTH_USER_MODEL', '')) != 'auth.User':
        return
    User = apps.get_model('auth', 'User')
    schema_editor.add_index(
        User, models.Index(fields=['email'], name='auth_user_email_idx')
    )


def _remove_email_index(apps, schema_editor):
    if str(getattr(settings, 'AUTH_USER_MODEL', '')) != 'auth.User':
        return
    User = apps.get_model('auth', 'User')
    schema_editor.remove_index(
        User, models.Index(fields=['email'], name='auth_user_email_idx')
    )


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0002_profile_stripe_billing'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        RunPython(_add_email_index, _remove_email_index, atomic=True),
    ]
