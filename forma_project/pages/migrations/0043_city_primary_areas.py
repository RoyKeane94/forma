from django.db import migrations

# City of London coverage catalogue (deduplicated, alphabetical).
CITY_AREAS = sorted({
    'Aldgate',
    'Aldgate East',
    'Bank',
    'Barbican',
    'Blackfriars',
    'Bond Street',
    'Borough',
    'Cannon Street',
    'Chancery Lane',
    'Charing Cross',
    'Covent Garden',
    'Fenchurch Street',
    'Farringdon',
    'Liverpool Street',
    'London Bridge',
    'Mansion House',
    'Moorgate',
    "St Paul's",
    'Old Street',
    'Oxford Circus',
    'Shoreditch',
    'Southwark',
    'Temple',
    'Tottenham Court Road',
})

AREA_DISTRICT_CODES = {
    'Aldgate': 'EC3',
    'Aldgate East': 'E1',
    'Bank': 'EC2',
    'Barbican': 'EC1',
    'Blackfriars': 'EC4',
    'Bond Street': 'W1',
    'Borough': 'SE1',
    'Cannon Street': 'EC4',
    'Chancery Lane': 'EC4',
    'Charing Cross': 'WC2',
    'Covent Garden': 'WC2',
    'Fenchurch Street': 'EC3',
    'Farringdon': 'EC1',
    'Liverpool Street': 'EC2',
    'London Bridge': 'SE1',
    'Mansion House': 'EC4',
    'Moorgate': 'EC2',
    'Old Street': 'EC1',
    'Oxford Circus': 'W1',
    'Shoreditch': 'EC2',
    'Southwark': 'SE1',
    "St Paul's": 'EC4',
    'Temple': 'WC2',
    'Tottenham Court Road': 'WC1',
}


def replace_city_primary_areas(apps, schema_editor):
    PostcodeDistrict = apps.get_model('pages', 'PostcodeDistrict')
    PrimaryArea = apps.get_model('pages', 'PrimaryArea')

    PrimaryArea.objects.all().delete()

    district_cache: dict[str, object] = {}
    for name in CITY_AREAS:
        code = AREA_DISTRICT_CODES.get(name, 'EC2')
        if code not in district_cache:
            district_cache[code], _ = PostcodeDistrict.objects.get_or_create(code=code)
        PrimaryArea.objects.create(name=name, district=district_cache[code])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0042_trainerprofile_profession'),
    ]

    operations = [
        migrations.RunPython(replace_city_primary_areas, noop_reverse),
    ]
