from django.db import migrations


def rename_back_pain_label(apps, schema_editor):
    ProofOutcomeTag = apps.get_model('pages', 'ProofOutcomeTag')
    ProofOutcomeTag.objects.filter(key='back_pain_gone').update(label='Pain gone')


class Migration(migrations.Migration):
    dependencies = [
        ('pages', '0037_sync_proof_outcome_tags_to_ten'),
    ]

    operations = [
        migrations.RunPython(rename_back_pain_label, migrations.RunPython.noop),
    ]
