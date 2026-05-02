from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest import mock

from .models import ProofTestimonial, TrainerProfile
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


class TrainerProofSubmissionTests(TestCase):
    def _create_profile(self) -> TrainerProfile:
        User = get_user_model()
        user = User.objects.create_user(
            username='proof_owner',
            email='proof_owner@example.com',
            password='pass1234',
        )
        return TrainerProfile.objects.create(
            user=user,
            first_name='Agi',
            last_name='Alexander',
            tagline='Trainer',
            bio='Bio',
            forma_made=False,
            is_published=True,
            completed_at=timezone.now(),
        )

    def _details_payload(self) -> dict:
        return {
            'proof_action': 'save_details',
            'client_first_name': 'Sam',
            'client_last_initial': 'J',
            'client_job_title': 'Designer',
            'star_rating': '5',
            'outcome_tags': ['built_strength', 'improved_mental_health'],
        }

    def test_proof_submission_page_is_public_for_published_profile(self):
        profile = self._create_profile()
        response = self.client.get(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug})
        )
        self.assertEqual(response.status_code, 200)

    def test_proof_submission_page_allows_incomplete_profile(self):
        profile = self._create_profile()
        profile.completed_at = None
        profile.save(update_fields=['completed_at'])
        response = self.client.get(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug})
        )
        self.assertEqual(response.status_code, 200)

    def test_multistep_submission_creates_pending_proof_testimonial(self):
        profile = self._create_profile()
        upload_payload = {
            'proof_action': 'upload_video',
            'video': SimpleUploadedFile(
                'clip.mp4',
                b'fake-video-content',
                content_type='video/mp4',
            ),
        }

        upload_response = self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=upload_payload,
        )
        self.assertEqual(upload_response.status_code, 302)
        self.assertIn('step=details', upload_response.url)

        details_response = self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=self._details_payload(),
        )
        self.assertEqual(details_response.status_code, 302)
        self.assertIn('step=preview', details_response.url)

        final_response = self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data={'proof_action': 'submit_testimonial'},
        )
        self.assertEqual(final_response.status_code, 302)
        submission = ProofTestimonial.objects.get(profile=profile)
        self.assertEqual(submission.status, ProofTestimonial.STATUS_PENDING)
        self.assertEqual(submission.client_first_name, 'Sam')
        self.assertEqual(
            submission.outcome_tags,
            ['built_strength', 'improved_mental_health'],
        )
        self.assertEqual(
            final_response.url,
            reverse('pages:trainer_proof_submit_success', kwargs={'profile_slug': profile.slug}),
        )

    def test_success_page_renders_after_submission(self):
        profile = self._create_profile()
        response = self.client.get(
            reverse('pages:trainer_proof_submit_success', kwargs={'profile_slug': profile.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your testimonial is submitted.')

    @mock.patch('pages.views._enqueue_suggested_quotes_generation')
    def test_multistep_submission_enqueues_ai_quote_generation(self, enqueue_mock):
        profile = self._create_profile()
        upload_payload = {
            'proof_action': 'upload_video',
            'video': SimpleUploadedFile(
                'clip.mp4',
                b'fake-video-content',
                content_type='video/mp4',
            ),
        }
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=upload_payload,
        )
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=self._details_payload(),
        )
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data={'proof_action': 'submit_testimonial'},
        )
        submission = ProofTestimonial.objects.get(profile=profile)
        enqueue_mock.assert_called_once_with(submission.pk)

    def test_details_step_rejects_more_than_two_outcome_tags(self):
        profile = self._create_profile()
        upload_payload = {
            'proof_action': 'upload_video',
            'video': SimpleUploadedFile(
                'clip.mp4',
                b'fake-video-content',
                content_type='video/mp4',
            ),
        }

        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=upload_payload,
        )

        payload = self._details_payload()
        payload['outcome_tags'] = [
            'built_strength',
            'improved_mental_health',
            'lost_weight',
        ]

        response = self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=payload,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choose one or two outcome tags.')
        self.assertEqual(ProofTestimonial.objects.filter(profile=profile).count(), 0)

    def test_preview_requires_video_and_details(self):
        profile = self._create_profile()
        response = self.client.get(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}) + '?step=preview'
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('step=upload', response.url)

    def test_post_rejects_more_than_two_outcome_tags(self):
        # Backwards-compatibility regression guard: direct details post still validated.
        profile = self._create_profile()
        upload_payload = {
            'proof_action': 'upload_video',
            'video': SimpleUploadedFile(
                'clip.mp4',
                b'fake-video-content',
                content_type='video/mp4',
            ),
        }
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=upload_payload,
        )
        payload = self._details_payload()
        payload['outcome_tags'] = [
            'built_strength',
            'improved_mental_health',
            'lost_weight',
        ]
        response = self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=payload,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choose one or two outcome tags.')
        self.assertEqual(ProofTestimonial.objects.filter(profile=profile).count(), 0)


class ProofApprovalWorkflowTests(TestCase):
    def _create_profile(self, username: str) -> TrainerProfile:
        User = get_user_model()
        user = User.objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password='pass1234',
        )
        return TrainerProfile.objects.create(
            user=user,
            first_name='Owner',
            last_name='Test',
            tagline='Trainer',
            bio='Bio',
            forma_made=False,
            is_published=True,
            completed_at=timezone.now(),
        )

    def _create_pending_submission(self, profile: TrainerProfile) -> ProofTestimonial:
        return ProofTestimonial.objects.create(
            profile=profile,
            client_first_name='Sam',
            client_last_initial='J',
            client_job_title='Designer',
            star_rating=5,
            outcome_tags=['built_strength'],
            prompt_start='Before',
            prompt_change='After',
            prompt_recommend='Recommend',
            video=SimpleUploadedFile(
                'clip.mp4',
                b'fake-video-content',
                content_type='video/mp4',
            ),
            status=ProofTestimonial.STATUS_PENDING,
        )

    def test_owner_can_approve_pending_submission(self):
        profile = self._create_profile('approver')
        submission = self._create_pending_submission(profile)
        submission.suggested_quotes = ['A great quote']
        submission.save(update_fields=['suggested_quotes'])
        self.client.login(username='approver', password='pass1234')

        response = self.client.post(
            reverse('pages:proof_notifications'),
            data={'submission_id': submission.pk, 'action': 'approve', 'pull_quote': 'A great quote'},
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, ProofTestimonial.STATUS_APPROVED)
        self.assertEqual(submission.pull_quote, 'A great quote')
        self.assertEqual(submission.reviewed_by, profile.user)
        self.assertIsNotNone(submission.reviewed_at)

    def test_owner_cannot_save_invalid_suggested_quote(self):
        profile = self._create_profile('approver_invalid_quote')
        submission = self._create_pending_submission(profile)
        submission.suggested_quotes = ['Valid quote']
        submission.save(update_fields=['suggested_quotes'])
        self.client.login(username='approver_invalid_quote', password='pass1234')

        response = self.client.post(
            reverse('pages:proof_notifications'),
            data={'submission_id': submission.pk, 'action': 'approve', 'pull_quote': 'Wrong quote'},
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, ProofTestimonial.STATUS_PENDING)
        self.assertEqual(submission.pull_quote, '')

    def test_owner_can_reject_pending_submission(self):
        profile = self._create_profile('rejector')
        submission = self._create_pending_submission(profile)
        video_name = submission.video.name
        self.client.login(username='rejector', password='pass1234')

        response = self.client.post(
            reverse('pages:proof_notifications'),
            data={'submission_id': submission.pk, 'action': 'reject'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProofTestimonial.objects.filter(pk=submission.pk).exists())
        self.assertFalse(default_storage.exists(video_name))

    def test_owner_cannot_review_another_trainers_submission(self):
        owner_profile = self._create_profile('owner_a')
        other_profile = self._create_profile('owner_b')
        submission = self._create_pending_submission(other_profile)
        self.client.login(username='owner_a', password='pass1234')

        response = self.client.post(
            reverse('pages:proof_notifications'),
            data={'submission_id': submission.pk, 'action': 'approve'},
        )

        self.assertEqual(response.status_code, 404)
        submission.refresh_from_db()
        self.assertEqual(submission.status, ProofTestimonial.STATUS_PENDING)

    def test_nav_shows_pending_notification_count(self):
        profile = self._create_profile('notify_owner')
        self._create_pending_submission(profile)
        self.client.login(username='notify_owner', password='pass1234')

        response = self.client.get(reverse('pages:my_account'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Notifications')
        self.assertEqual(response.context['proof_pending_approvals_count'], 1)

    def test_my_account_counts_only_approved_and_shows_review_link(self):
        profile = self._create_profile('account_counts_owner')
        self.client.login(username='account_counts_owner', password='pass1234')
        approved = self._create_pending_submission(profile)
        approved.status = ProofTestimonial.STATUS_APPROVED
        approved.reviewed_at = timezone.now()
        approved.reviewed_by = profile.user
        approved.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
        self._create_pending_submission(profile)

        response = self.client.get(reverse('pages:my_account'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['testimonial_total_count'], 1)
        self.assertEqual(response.context['testimonial_to_review_count'], 1)
        self.assertContains(response, reverse('pages:proof_notifications'))

    def test_my_account_shows_submission_and_public_proof_links(self):
        profile = self._create_profile('account_links_owner')
        self.client.login(username='account_links_owner', password='pass1234')

        response = self.client.get(reverse('pages:my_account'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Client testimonial link')
        self.assertContains(response, 'Public proof page')
        self.assertContains(
            response,
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
        )
        self.assertContains(response, profile.get_absolute_url())

    def test_notifications_page_includes_my_testimonials_link(self):
        self._create_profile('notifications_link_owner')
        self.client.login(username='notifications_link_owner', password='pass1234')

        response = self.client.get(reverse('pages:proof_notifications'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('pages:proof_testimonials_page'))

    def test_my_testimonials_page_lists_approved_only(self):
        profile = self._create_profile('approved_only_owner')
        self.client.login(username='approved_only_owner', password='pass1234')
        approved = self._create_pending_submission(profile)
        approved.status = ProofTestimonial.STATUS_APPROVED
        approved.reviewed_at = timezone.now()
        approved.reviewed_by = profile.user
        approved.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
        pending = self._create_pending_submission(profile)
        pending.client_first_name = 'Pending'
        pending.save(update_fields=['client_first_name'])

        response = self.client.get(reverse('pages:proof_testimonials_page'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sam J.')
        self.assertNotContains(response, 'Pending J.')
