import django.db.models.deletion
from django.db import migrations, models


# Same catalogue as former onboarding AREAS (name → outward district code).
AREAS_SEED = [
    ('Balham', 'SW12'),
    ('Barnes', 'SW13'),
    ('Battersea', 'SW11'),
    ('Bermondsey', 'SE1'),
    ('Brixton', 'SW2'),
    ('Camberwell', 'SE5'),
    ('Chelsea', 'SW3'),
    ('Clapham', 'SW4'),
    ('Dulwich', 'SE21'),
    ('East Sheen', 'SW14'),
    ('Elephant & Castle', 'SE1'),
    ('Fulham', 'SW6'),
    ('Herne Hill', 'SE24'),
    ('Kennington', 'SE11'),
    ('Kew', 'TW9'),
    ('Mortlake', 'SW14'),
    ('New Malden', 'KT3'),
    ('Oval', 'SE11'),
    ('Peckham', 'SE15'),
    ('Putney', 'SW15'),
    ('Richmond', 'TW10'),
    ('Roehampton', 'SW15'),
    ('South Wimbledon', 'SW19'),
    ('Stockwell', 'SW9'),
    ('Streatham', 'SW16'),
    ('Surbiton', 'KT6'),
    ('Tooting', 'SW17'),
    ('Tulse Hill', 'SE27'),
    ('Vauxhall', 'SE11'),
    ('Wandsworth', 'SW18'),
    ('Wimbledon', 'SW19'),
]


def seed_areas(apps, schema_editor):
    PostcodeDistrict = apps.get_model('pages', 'PostcodeDistrict')
    PrimaryArea = apps.get_model('pages', 'PrimaryArea')
    codes = {}
    for _name, code in AREAS_SEED:
        if code not in codes:
            d, _ = PostcodeDistrict.objects.get_or_create(code=code)
            codes[code] = d
    for name, code in AREAS_SEED:
        district = codes[code]
        PrimaryArea.objects.get_or_create(name=name, defaults={'district': district})


def link_profiles(apps, schema_editor):
    TrainerProfile = apps.get_model('pages', 'TrainerProfile')
    PrimaryArea = apps.get_model('pages', 'PrimaryArea')
    for row in TrainerProfile.objects.all():
        name = (row.primary_area or '').strip()
        pc = (row.postcode_district or '').strip()
        if not name:
            continue
        pa = None
        if pc:
            pa = PrimaryArea.objects.filter(name=name, district__code=pc).first()
        if pa is None:
            pa = PrimaryArea.objects.filter(name=name).first()
        if pa is not None:
            row.primary_area_fk_id = pa.pk
            row.save(update_fields=['primary_area_fk_id'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0004_trainerprofile_forma_made_urls'),
    ]

    operations = [
        migrations.CreateModel(
            name='PostcodeDistrict',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=16, unique=True)),
            ],
            options={
                'db_table': 'pages_postcode_district',
                'ordering': ['code'],
            },
        ),
        migrations.CreateModel(
            name='PrimaryArea',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128, unique=True)),
                (
                    'district',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='primary_areas',
                        to='pages.postcodedistrict',
                    ),
                ),
            ],
            options={
                'db_table': 'pages_primary_area',
                'ordering': ['name'],
            },
        ),
        migrations.RunPython(seed_areas, noop_reverse),
        migrations.AddField(
            model_name='trainerprofile',
            name='primary_area_fk',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='trainer_profiles',
                to='pages.primaryarea',
            ),
        ),
        migrations.RunPython(link_profiles, noop_reverse),
        migrations.RemoveField(
            model_name='trainerprofile',
            name='primary_area',
        ),
        migrations.RemoveField(
            model_name='trainerprofile',
            name='postcode_district',
        ),
        migrations.RenameField(
            model_name='trainerprofile',
            old_name='primary_area_fk',
            new_name='primary_area',
        ),
    ]
