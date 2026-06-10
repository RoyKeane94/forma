from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_profile_welcome_email_sent_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='WaitlistSignup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'verbose_name': 'waitlist signup',
                'verbose_name_plural': 'waitlist signups',
                'db_table': 'accounts_waitlist_signup',
                'ordering': ['-created_at'],
            },
        ),
    ]
