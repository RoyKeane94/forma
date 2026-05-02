from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from pages.models import PostcodeDistrict, PrimaryArea


class RegistrationFlowTests(TestCase):
    def setUp(self):
        district = PostcodeDistrict.objects.create(code='SW12')
        self.primary_area = PrimaryArea.objects.create(name='Clapham', district=district)

    def test_register_redirects_to_my_account_with_testimonial_next_step(self):
        response = self.client.post(
            reverse('accounts:register'),
            data={
                'first_name': 'Agi',
                'last_name': 'Alexander',
                'email': 'new@example.com',
                'password1': 'StrongPass123!',
                'password2': 'StrongPass123!',
                'accept_terms': 'on',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], reverse('pages:my_account'))
        self.assertContains(response, 'Get your first testimonial')
        self.assertContains(response, 'Don&apos;t worry, you get to approve it before it goes live.')
        User = get_user_model()
        user = User.objects.get(email='new@example.com')
        self.assertEqual(user.first_name, 'Agi')
        self.assertEqual(user.last_name, 'Alexander')

    def test_register_requires_first_and_last_name(self):
        response = self.client.post(
            reverse('accounts:register'),
            data={
                'email': 'missing-names@example.com',
                'password1': 'StrongPass123!',
                'password2': 'StrongPass123!',
                'accept_terms': 'on',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter your first name.')
        self.assertContains(response, 'Enter your last name.')
        User = get_user_model()
        self.assertFalse(User.objects.filter(email='missing-names@example.com').exists())

    def test_name_step_saves_names_and_shows_proof_link(self):
        User = get_user_model()
        user = User.objects.create_user(
            username='name-step@example.com',
            email='name-step@example.com',
            password='StrongPass123!',
        )
        self.client.login(username=user.username, password='StrongPass123!')

        response = self.client.post(
            reverse('accounts:register_name'),
            data={
                'first_name': 'Agi',
                'last_name': 'Alexander',
                'primary_area': str(self.primary_area.pk),
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Agi')
        self.assertEqual(user.last_name, 'Alexander')
        self.assertContains(response, 'Get your first testimonial')
        self.assertContains(response, '/agi-alexander/submit/')

    def test_name_step_does_not_prefill_placeholder_names(self):
        User = get_user_model()
        user = User.objects.create_user(
            username='placeholder@example.com',
            email='placeholder@example.com',
            password='StrongPass123!',
        )
        self.client.login(username=user.username, password='StrongPass123!')
        response = self.client.get(reverse('accounts:register_name'))
        self.assertNotContains(response, 'value="Mark"')
        self.assertNotContains(response, 'value="Jobs"')

    def test_name_step_clears_legacy_mark_jobs_profile_values(self):
        User = get_user_model()
        user = User.objects.create_user(
            username='legacy-defaults@example.com',
            email='legacy-defaults@example.com',
            password='StrongPass123!',
            first_name='',
            last_name='',
        )
        from pages.models import TrainerProfile

        TrainerProfile.objects.create(
            user=user,
            first_name='Mark',
            last_name='Jobs',
            tagline='',
            bio='',
        )
        self.client.login(username=user.username, password='StrongPass123!')

        response = self.client.get(reverse('accounts:register_name'))
        self.assertNotContains(response, 'value="Mark"')
        self.assertNotContains(response, 'value="Jobs"')
