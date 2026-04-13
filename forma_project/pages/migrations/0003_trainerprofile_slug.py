from django.db import migrations, models
from django.utils.text import slugify


def _slug_column_exists(schema_editor) -> bool:
    connection = schema_editor.connection
    table = 'pages_trainer_profile'
    column = 'slug'
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s
                  AND column_name = %s
                """,
                [table, column],
            )
            return cursor.fetchone() is not None
        if connection.vendor == 'sqlite':
            cursor.execute('PRAGMA table_info(%s)' % table)
            return any(row[1] == column for row in cursor.fetchall())
        desc = connection.introspection.get_table_description(cursor, table)
        return any(row.name == column for row in desc)


def add_slug_column_if_missing(apps, schema_editor):
    """
    DB-only add (do not use apps / add_field: SeparateDatabaseAndState passes
    from_state without this field to RunPython).
    """
    if _slug_column_exists(schema_editor):
        return
    connection = schema_editor.connection
    qtable = connection.ops.quote_name('pages_trainer_profile')
    qcol = connection.ops.quote_name('slug')
    if connection.vendor == 'postgresql':
        schema_editor.execute(
            f'ALTER TABLE {qtable} ADD COLUMN IF NOT EXISTS {qcol} varchar(255) NULL'
        )
    else:
        schema_editor.execute(
            f'ALTER TABLE {qtable} ADD COLUMN {qcol} varchar(255) NULL'
        )


def populate_slugs(apps, schema_editor):
    TrainerProfile = apps.get_model('pages', 'TrainerProfile')

    def base_for(first_name: str, last_name: str) -> str:
        a, b = slugify((first_name or '').strip()), slugify((last_name or '').strip())
        parts = [x for x in (a, b) if x]
        return '-'.join(parts) if parts else 'trainer'

    for profile in TrainerProfile.objects.order_by('pk'):
        base = base_for(profile.first_name, profile.last_name)
        candidate = base
        n = 2
        while TrainerProfile.objects.filter(slug=candidate).exclude(pk=profile.pk).exists():
            candidate = f'{base}-{n}'
            n += 1
        profile.slug = candidate
        profile.save(update_fields=['slug'])


# PostgreSQL: slug indexes can live outside `public` (e.g. Railway).
_DROP_SLUG_PG_ARTIFACTS = r"""
DO $forma_drop_slug$
DECLARE r RECORD;
BEGIN
  -- Constraints first: unique indexes named ...slug..._uniq are owned by
  -- constraints; DROP INDEX on them raises DependentObjectsStillExist.
  FOR r IN (
    SELECT n.nspname AS ns, t.relname AS tbl, c.conname AS con
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE c.contype = 'u'
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND t.relname = 'pages_trainer_profile'
      AND c.conname ~ '^pages_trainer_profile_slug_'
  ) LOOP
    EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT IF EXISTS %I CASCADE', r.ns, r.tbl, r.con);
  END LOOP;
  FOR r IN (
    SELECT n.nspname AS ns, c.relname AS idx
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('i', 'I')
      AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
      AND c.relname LIKE 'pages_trainer_profile_slug%'
  ) LOOP
    EXECUTE format('DROP INDEX IF EXISTS %I.%I CASCADE', r.ns, r.idx);
  END LOOP;
END $forma_drop_slug$;
"""


def drop_pg_slug_constraints_and_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(_DROP_SLUG_PG_ARTIFACTS)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('pages', '0002_trainerprofile_is_published'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='trainerprofile',
                    name='slug',
                    field=models.SlugField(
                        blank=True,
                        max_length=255,
                        null=True,
                        db_index=False,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    add_slug_column_if_missing,
                    migrations.RunPython.noop,
                ),
            ],
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
        migrations.RunPython(
            drop_pg_slug_constraints_and_indexes,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='trainerprofile',
            name='slug',
            field=models.SlugField(
                help_text='Public URL segment: firstname-lastname (with numeric suffix if needed).',
                max_length=255,
                unique=True,
                blank=False,
                db_index=False,
            ),
        ),
    ]
