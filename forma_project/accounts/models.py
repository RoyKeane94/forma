from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Per-user record for Forma; extend with PT fields later."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )

    class Meta:
        db_table = 'accounts_profile'

    def __str__(self):
        return f'Profile({self.user.get_username()})'
