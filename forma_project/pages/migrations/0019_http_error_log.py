import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pages', '0018_chiswick_st_margarets_primary_areas'),
    ]

    operations = [
        migrations.CreateModel(
            name='HttpErrorLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status_code', models.PositiveSmallIntegerField(db_index=True)),
                ('path', models.CharField(blank=True, default='', max_length=2048)),
                ('query_string', models.CharField(blank=True, default='', max_length=2048)),
                ('method', models.CharField(blank=True, default='', max_length=16)),
                ('message', models.TextField(blank=True, default='')),
                ('details', models.TextField(blank=True, default='')),
                ('exception_type', models.CharField(blank=True, default='', max_length=255)),
                ('ip', models.CharField(blank=True, default='', max_length=45)),
                ('referrer', models.CharField(blank=True, default='', max_length=2048)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    'user',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='+',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'db_table': 'pages_http_error_log',
                'ordering': ['-created_at'],
            },
        ),
    ]
