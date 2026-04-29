from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import TrainerProfile
from .views import _finalize_keep_forma_profile


class TrainerPublicProfileVisibilityTests(TestCase):
    def _create_profile(
        self,
        *,
        username: str,
        first_name: str,
        last_name: str,
        forma_made: bool,
        is_published: bool,
        completed: bool = False,
    ) -> TrainerProfile:
        User = get_user_model()
        user = User.objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password='pass1234',
        )
        return TrainerProfile.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            tagline='Trainer',
            bio='Bio',
            forma_made=forma_made,
            is_published=is_published,
            completed_at=timezone.now() if completed else None,
        )

    def test_anonymous_can_view_forma_made_keyed_url_when_unpublished(self):
        profile = self._create_profile(
            username='forma_trainer',
            first_name='Agi',
            last_name='Alexander',
            forma_made=True,
            is_published=False,
        )

        response = self.client.get(
            reverse(
                'pages:trainer_profile_forma',
                kwargs={'profile_slug': profile.slug, 'url_key': profile.public_url_key},
            )
        )

        self.assertEqual(response.status_code, 200)

    def test_anonymous_cannot_view_unpublished_self_serve_profile(self):
        profile = self._create_profile(
            username='self_serve_trainer',
            first_name='Jamie',
            last_name='Stone',
            forma_made=False,
            is_published=False,
            completed=True,
        )

        response = self.client.get(
            reverse('pages:trainer_profile', kwargs={'profile_slug': profile.slug})
        )

        self.assertEqual(response.status_code, 404)

    def test_claiming_forma_profile_marks_it_published(self):
        profile = self._create_profile(
            username='forma_claim_source',
            first_name='Claim',
            last_name='Target',
            forma_made=True,
            is_published=False,
        )

        claimed_user, err = _finalize_keep_forma_profile(
            profile_id=profile.pk,
            email='claimer@example.com',
            password='StrongPass123!',
        )

        self.assertIsNotNone(claimed_user)
        self.assertIsNone(err)
        profile.refresh_from_db()
        self.assertFalse(profile.forma_made)
        self.assertIsNone(profile.public_url_key)
        self.assertTrue(profile.is_published)
