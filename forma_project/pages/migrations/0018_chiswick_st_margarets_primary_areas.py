from django.db import migrations


EXTRA_AREAS = [
    ('Chiswick', 'W4'),
    ('St Margarets', 'TW1'),
]


def seed_extra_primary_areas(apps, schema_editor):
    PostcodeDistrict = apps.get_model('pages', 'PostcodeDistrict')
    PrimaryArea = apps.get_model('pages', 'PrimaryArea')
    for name, code in EXTRA_AREAS:
        district, _ = PostcodeDistrict.objects.get_or_create(code=code)
        PrimaryArea.objects.get_or_create(name=name, defaults={'district': district})


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0017_alter_trainerprofile_client_reviews'),
    ]

    operations = [
        migrations.RunPython(seed_extra_primary_areas, noop_reverse),
    ]
