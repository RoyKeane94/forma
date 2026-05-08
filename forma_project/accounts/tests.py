from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from unittest import mock

from pages.models import (
    PostcodeDistrict,
    PrimaryArea,
    ProofTestimonial,
    TrainerGalleryPhoto,
    TrainerProfile,
)


class RegistrationFlowTests(TestCase):
    def setUp(self):
        district, _ = PostcodeDistrict.objects.get_or_create(code='SW12')
        self.primary_area, _ = PrimaryArea.objects.get_or_create(
            name='Clapham',
            defaults={'district': district},
        )

    @mock.patch('accounts.views.create_register_checkout_session')
    @mock.patch('accounts.views.stripe_register_configured', return_value=True)
    def test_register_redirects_to_stripe_checkout_without_creating_account(
        self,
        _stripe_configured_mock,
        create_checkout_mock,
    ):
        create_checkout_mock.return_value = 'https://checkout.stripe.com/test-session'
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
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://checkout.stripe.com/test-session')
        create_checkout_mock.assert_called_once()
        User = get_user_model()
        self.assertFalse(User.objects.filter(email='new@example.com').exists())

    @mock.patch('accounts.views.stripe_register_configured', return_value=True)
    @mock.patch('accounts.views.retrieve_checkout_session')
    @mock.patch('accounts.views.complete_pending_registration_from_stripe_session')
    @mock.patch('accounts.views.send_mail')
    def test_register_checkout_success_creates_session_login_and_redirects(
        self,
        send_mail_mock,
        complete_pending_mock,
        retrieve_session_mock,
        _stripe_configured_mock,
    ):
        class FakeStripeSession:
            status = 'complete'
            mode = 'subscription'
            payment_status = 'paid'
            customer = None
            subscription = None
            metadata = {'purpose': 'register_account', 'pending_token': 'abc123'}

        User = get_user_model()
        user = User.objects.create_user(
            username='paid@example.com',
            email='paid@example.com',
            password='StrongPass123!',
            first_name='Paid',
            last_name='User',
        )
        retrieve_session_mock.return_value = FakeStripeSession()
        complete_pending_mock.return_value = (user, None)

        response = self.client.get(
            reverse('accounts:register_checkout_success') + '?session_id=cs_test_123'
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('pages:my_account'))
        self.assertTrue('_auth_user_id' in self.client.session)
        profile = TrainerProfile.objects.get(user=user)
        expected_link = f"/{profile.slug}/submit/"
        send_mail_mock.assert_called_once()
        self.assertIn('Welcome to Forma', send_mail_mock.call_args.kwargs['subject'])
        self.assertIn(expected_link, send_mail_mock.call_args.kwargs['message'])

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


class AccountDeletionMediaCleanupTests(TestCase):
    def test_delete_account_removes_associated_media_files(self):
        User = get_user_model()
        user = User.objects.create_user(
            username='delete-media-user@example.com',
            email='delete-media-user@example.com',
            password='StrongPass123!',
        )
        profile = TrainerProfile.objects.create(
            user=user,
            first_name='Delete',
            last_name='Media',
            tagline='Trainer',
            bio='Bio',
        )
        profile.portrait = 'trainer/portraits/portrait.jpg'
        profile.intro_video = 'trainer/intro/intro.mp4'
        profile.save(update_fields=['portrait', 'intro_video'])
        TrainerGalleryPhoto.objects.create(
            profile=profile,
            slot=7,
            image='trainer/gallery/gallery.jpg',
        )
        ProofTestimonial.objects.create(
            profile=profile,
            client_first_name='Sam',
            client_last_initial='J',
            client_job_title='Designer',
            star_rating=5,
            outcome_tags=['built_strength'],
            prompt_start='Before',
            prompt_change='After',
            prompt_recommend='Recommend',
            video='proof/videos/testimonial.mp4',
            poster='proof/posters/testimonial.jpg',
            status=ProofTestimonial.STATUS_APPROVED,
        )

        self.client.login(username=user.username, password='StrongPass123!')
        with mock.patch('accounts.media_cleanup.default_storage.exists', return_value=True), mock.patch(
            'accounts.media_cleanup.default_storage.delete'
        ) as delete_mock:
            response = self.client.post(
                reverse('accounts:delete_account'),
                data={'password': 'StrongPass123!'},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:account_deleted'))
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

        deleted_paths = {call.args[0] for call in delete_mock.call_args_list}
        self.assertEqual(
            deleted_paths,
            {
                'trainer/portraits/portrait.jpg',
                'trainer/intro/intro.mp4',
                'trainer/gallery/gallery.jpg',
                'proof/videos/testimonial.mp4',
                'proof/posters/testimonial.jpg',
            },
        )

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
