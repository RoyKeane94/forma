import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pages', '0003_trainerprofile_slug'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainerprofile',
            name='forma_made',
            field=models.BooleanField(
                default=False,
                help_text='Profile created by a Forma superuser; public URL uses /first-last/KEY/.',
            ),
        ),
        migrations.AddField(
            model_name='trainerprofile',
            name='public_url_key',
            field=models.CharField(
                blank=True,
                help_text='Five random characters for Forma-made public URLs only.',
                max_length=5,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='trainerprofile',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='trainer_profiles_created',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='trainerprofile',
            name='slug',
            field=models.SlugField(
                help_text='URL first segment (first-last). Unique for self-serve; Forma-made shares base across keys.',
                max_length=255,
                unique=False,
            ),
        ),
        migrations.AddConstraint(
            model_name='trainerprofile',
            constraint=models.UniqueConstraint(
                condition=models.Q(forma_made=False),
                fields=('slug',),
                name='pages_trainer_selfserve_slug_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='trainerprofile',
            constraint=models.UniqueConstraint(
                condition=models.Q(forma_made=True),
                fields=('slug', 'public_url_key'),
                name='pages_trainer_forma_slug_key_uniq',
            ),
        ),
    ]
