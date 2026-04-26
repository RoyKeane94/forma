# Create django cache table for DatabaseCache in production (multi-worker).
# Safe no-op in local dev where LocMem is used instead.

from django.conf import settings
from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    if (
        settings.CACHES.get('default', {}).get('BACKEND')
        != 'django.core.cache.backends.db.DatabaseCache'
    ):
        return
    table = settings.CACHES['default']['LOCATION']
    call_command(
        'createcachetable',
        table,
        database=schema_editor.connection.alias,
        verbosity=0,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0028_alter_featured_review_slot_max'),
    ]

    operations = [
        migrations.RunPython(create_cache_table, noop),
    ]
