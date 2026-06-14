from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from unittest import mock

from .models import ProofTestimonial, TrainerProfile
from .profile_display import PROOF_PAGE_MIN_LIVE_TESTIMONIALS
from .views import _finalize_keep_forma_profile


def _create_live_proof_testimonials(profile: TrainerProfile, count: int = PROOF_PAGE_MIN_LIVE_TESTIMONIALS) -> None:
    for i in range(count):
        ProofTestimonial.objects.create(
            profile=profile,
            client_first_name=f'Client{i}',
            client_last_initial='A',
            client_job_title='Designer',
            star_rating=5,
            outcome_tags=['built_strength'],
            prompt_start='Before',
            prompt_change='After',
            prompt_recommend='Recommend',
            video=SimpleUploadedFile(
                f'clip-{i}.mp4',
                b'fake-video-content',
                content_type='video/mp4',
            ),
            status=ProofTestimonial.STATUS_APPROVED,
            reviewed_at=timezone.now(),
        )


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

    def test_public_proof_route_uses_same_template_as_account_proof_page(self):
        profile = self._create_profile(
            username='proof_page_trainer',
            first_name='Agi',
            last_name='Alexander',
            forma_made=False,
            is_published=True,
            completed=True,
        )
        _create_live_proof_testimonials(profile)

        response = self.client.get(
            reverse('pages:trainer_profile_proof', kwargs={'profile_slug': profile.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pages/proof_testimonials_page.html')

    def test_public_proof_hidden_until_three_live_testimonials(self):
        profile = self._create_profile(
            username='proof_gate_trainer',
            first_name='Agi',
            last_name='Alexander',
            forma_made=False,
            is_published=True,
            completed=True,
        )
        _create_live_proof_testimonials(profile, count=PROOF_PAGE_MIN_LIVE_TESTIMONIALS - 1)
        proof_url = reverse('pages:trainer_profile_proof', kwargs={'profile_slug': profile.slug})

        anonymous_response = self.client.get(proof_url)
        self.assertEqual(anonymous_response.status_code, 404)

        self.client.login(username='proof_gate_trainer', password='pass1234')
        owner_response = self.client.get(proof_url)
        self.assertEqual(owner_response.status_code, 200)
        self.assertTrue(owner_response.context['proof_page_preview_only'])
        self.assertContains(owner_response, 'Preview only.')

    def test_public_proof_visible_when_unpublished(self):
        profile = self._create_profile(
            username='proof_unpublished',
            first_name='Sam',
            last_name='River',
            forma_made=False,
            is_published=False,
            completed=False,
        )
        _create_live_proof_testimonials(profile)

        response = self.client.get(
            reverse('pages:trainer_profile_proof', kwargs={'profile_slug': profile.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pages/proof_testimonials_page.html')

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

    def _submit_payload(self, *, marketing_consent: bool = False) -> dict:
        payload = {
            'proof_action': 'submit_testimonial',
            'accept_video_submission_terms': 'on',
        }
        if marketing_consent:
            payload['forma_marketing_consent'] = 'on'
        return payload

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

    @mock.patch('pages.views.poster_bytes_from_video_file', return_value=b'poster-bytes')
    def test_multistep_submission_creates_pending_proof_testimonial(self, _poster_mock):
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
            data=self._submit_payload(),
        )
        self.assertEqual(final_response.status_code, 302)
        submission = ProofTestimonial.objects.get(profile=profile)
        self.assertEqual(submission.status, ProofTestimonial.STATUS_PENDING)
        self.assertEqual(submission.client_first_name, 'Sam')
        self.assertTrue((submission.video.name or '').startswith('proof/videos/'))
        self.assertEqual(
            submission.outcome_tags,
            ['built_strength', 'improved_mental_health'],
        )
        self.assertEqual(
            final_response.url,
            reverse('pages:trainer_proof_submit_success', kwargs={'profile_slug': profile.slug}),
        )
        self.assertIsNotNone(submission.video_submission_terms_accepted_at)
        self.assertFalse(submission.forma_marketing_consent)

    @override_settings(SYNC_PROOF_REVIEW_EMAIL=True)
    @mock.patch('pages.views.poster_bytes_from_video_file', return_value=b'poster-bytes')
    @mock.patch('pages.proof_emails.send_mail')
    def test_submission_sends_review_email_to_owner(self, send_mail_mock, _poster_mock):
        profile = self._create_profile()
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data={
                'proof_action': 'upload_video',
                'video': SimpleUploadedFile('clip.mp4', b'fake-video-content', content_type='video/mp4'),
            },
        )
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=self._details_payload(),
        )
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=self._submit_payload(),
        )

        send_mail_mock.assert_called_once()
        kwargs = send_mail_mock.call_args.kwargs
        self.assertEqual(kwargs['subject'], 'New testimonial to review')
        self.assertIn('Hi Agi,', kwargs['message'])
        self.assertIn('A client just submitted a testimonial for your Forma profile.', kwargs['message'])
        self.assertIn(reverse('pages:proof_notifications'), kwargs['message'])
        self.assertIn('Tom\n\nForma', kwargs['message'])
        self.assertEqual(kwargs['recipient_list'], ['proof_owner@example.com'])

    def test_submit_requires_video_submission_terms(self):
        profile = self._create_profile()
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data={
                'proof_action': 'upload_video',
                'video': SimpleUploadedFile('clip.mp4', b'fake-video-content', content_type='video/mp4'),
            },
        )
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=self._details_payload(),
        )
        response = self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data={'proof_action': 'submit_testimonial'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please agree to the Video Submission Terms')
        self.assertEqual(ProofTestimonial.objects.filter(profile=profile).count(), 0)

    @mock.patch('pages.views.poster_bytes_from_video_file', return_value=b'poster-bytes')
    def test_submit_stores_forma_marketing_consent_when_opted_in(self, _poster_mock):
        profile = self._create_profile()
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data={
                'proof_action': 'upload_video',
                'video': SimpleUploadedFile('clip.mp4', b'fake-video-content', content_type='video/mp4'),
            },
        )
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=self._details_payload(),
        )
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=self._submit_payload(marketing_consent=True),
        )
        submission = ProofTestimonial.objects.get(profile=profile)
        self.assertTrue(submission.forma_marketing_consent)

    def test_success_page_renders_after_submission(self):
        profile = self._create_profile()
        response = self.client.get(
            reverse('pages:trainer_proof_submit_success', kwargs={'profile_slug': profile.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You're a good client.")

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
            data=self._submit_payload(),
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

    @mock.patch('pages.views.default_storage')
    def test_details_step_allows_missing_star_rating(self, storage_mock):
        profile = self._create_profile()
        video_key = 'proof/tmp/direct_clip.mp4'
        storage_mock.exists.return_value = True
        storage_mock.size.return_value = len(b'fake-video-content')
        self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data={
                'proof_action': 'upload_video_direct',
                'video_key': video_key,
                'video_name': 'clip.mp4',
            },
        )
        payload = self._details_payload()
        payload.pop('star_rating', None)
        response = self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data=payload,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('step=preview', response.url)
        draft = self.client.session.get(f'proof_draft_{profile.pk}') or {}
        self.assertEqual(int((draft.get('details') or {}).get('star_rating') or 0), 5)

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

    @mock.patch('pages.views.default_storage')
    def test_direct_upload_reference_moves_to_details_step(self, storage_mock):
        profile = self._create_profile()
        video_key = 'proof/tmp/direct_clip.mp4'
        storage_mock.exists.return_value = True
        storage_mock.size.return_value = len(b'fake-video-content')

        response = self.client.post(
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
            data={
                'proof_action': 'upload_video_direct',
                'video_key': video_key,
                'video_name': 'clip.mp4',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('step=details', response.url)
        draft = self.client.session.get(f'proof_draft_{profile.pk}')
        self.assertEqual(draft.get('video_path'), video_key)

    @override_settings(AWS_STORAGE_BUCKET_NAME='')
    def test_presign_endpoint_returns_400_when_direct_upload_disabled(self):
        profile = self._create_profile()
        response = self.client.post(
            reverse('pages:trainer_proof_upload_presign', kwargs={'profile_slug': profile.slug}),
            data={
                'filename': 'clip.mp4',
                'content_type': 'video/mp4',
                'size': '1024',
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    @override_settings(
        AWS_STORAGE_BUCKET_NAME='forma-test-bucket',
        AWS_S3_REGION_NAME='eu-north-1',
        AWS_ACCESS_KEY_ID='key',
        AWS_SECRET_ACCESS_KEY='secret',
    )
    @mock.patch('pages.views.boto3')
    def test_presign_endpoint_returns_upload_url(self, boto3_mock):
        profile = self._create_profile()
        s3_client = boto3_mock.client.return_value
        s3_client.generate_presigned_url.return_value = 'https://example.test/presigned'

        response = self.client.post(
            reverse('pages:trainer_proof_upload_presign', kwargs={'profile_slug': profile.slug}),
            data={
                'filename': 'clip.mp4',
                'content_type': 'video/mp4',
                'size': '1024',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['upload_url'], 'https://example.test/presigned')
        self.assertTrue(payload['video_key'].startswith('proof/tmp/'))
        boto3_mock.client.assert_called_once()


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
        self.assertContains(response, 'Reviews')
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
        self.assertContains(response, 'Review now')
        self.assertContains(response, 'waiting for your approval')
        self.assertContains(response, reverse('pages:proof_notifications'))
        self.assertContains(response, reverse('pages:proof_testimonials_edit'))

    def test_my_account_shows_submission_and_public_proof_links(self):
        profile = self._create_profile('account_links_owner')
        proof_url = reverse('pages:trainer_profile_proof', kwargs={'profile_slug': profile.slug})
        self.client.login(username='account_links_owner', password='pass1234')

        response = self.client.get(reverse('pages:my_account'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Client testimonial link')
        self.assertContains(response, 'Proof page')
        self.assertNotContains(response, proof_url)
        self.assertContains(response, 'not accessible to the public')
        self.assertContains(response, '0 of 3')
        self.assertContains(response, reverse('pages:proof_testimonials_page'))
        self.assertContains(
            response,
            reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
        )

        _create_live_proof_testimonials(profile, count=PROOF_PAGE_MIN_LIVE_TESTIMONIALS - 1)
        response = self.client.get(reverse('pages:my_account'))
        self.assertNotContains(response, proof_url)
        self.assertContains(response, '2 of 3')
        self.assertContains(response, 'Preview proof page')

        _create_live_proof_testimonials(profile, count=1)
        response = self.client.get(reverse('pages:my_account'))
        self.assertContains(response, proof_url)
        self.assertContains(response, 'Public proof page')

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

    def test_edit_testimonials_page_lists_approved_only(self):
        profile = self._create_profile('edit_page_owner')
        self.client.login(username='edit_page_owner', password='pass1234')
        approved = self._create_pending_submission(profile)
        approved.status = ProofTestimonial.STATUS_APPROVED
        approved.reviewed_at = timezone.now()
        approved.reviewed_by = profile.user
        approved.pull_quote = 'Big confidence boost'
        approved.save(update_fields=['status', 'reviewed_at', 'reviewed_by', 'pull_quote'])
        pending = self._create_pending_submission(profile)
        pending.client_first_name = 'Pending'
        pending.save(update_fields=['client_first_name'])

        response = self.client.get(reverse('pages:proof_testimonials_edit'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit testimonials')
        self.assertContains(response, 'Sam J.')
        self.assertContains(response, 'Designer')
        self.assertContains(response, 'Big confidence boost')
        self.assertNotContains(response, 'Pending J.')

    def test_owner_can_delete_approved_testimonial_from_edit_page(self):
        profile = self._create_profile('edit_delete_owner')
        self.client.login(username='edit_delete_owner', password='pass1234')
        approved = self._create_pending_submission(profile)
        approved.status = ProofTestimonial.STATUS_APPROVED
        approved.reviewed_at = timezone.now()
        approved.reviewed_by = profile.user
        approved.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
        video_name = approved.video.name

        response = self.client.post(
            reverse('pages:proof_testimonials_edit'),
            data={'submission_id': approved.pk, 'action': 'delete'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProofTestimonial.objects.filter(pk=approved.pk).exists())
        self.assertFalse(default_storage.exists(video_name))


class StripeWebhookRegistrationTests(TestCase):
    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_test')
    @mock.patch('accounts.views._enqueue_post_registration_tasks')
    @mock.patch('pages.views.save_checkout_billing_ids')
    @mock.patch('pages.views.complete_pending_registration_from_stripe_session')
    @mock.patch('pages.views.retrieve_checkout_session')
    @mock.patch('stripe.Webhook.construct_event')
    def test_register_webhook_sends_founder_welcome_email(
        self,
        construct_event_mock,
        retrieve_session_mock,
        complete_pending_mock,
        _save_billing_ids_mock,
        post_registration_mock,
    ):
        User = get_user_model()
        user = User.objects.create_user(
            username='webhook-new-user@example.com',
            email='webhook-new-user@example.com',
            password='StrongPass123!',
            first_name='Webhook',
            last_name='User',
        )

        class FakeStripeSession:
            status = 'complete'
            mode = 'subscription'
            payment_status = 'paid'
            customer = None
            subscription = None
            metadata = {'purpose': 'register_account', 'pending_token': 'abc123'}

        construct_event_mock.return_value = {
            'type': 'checkout.session.completed',
            'data': {'object': {'id': 'cs_test_123', 'metadata': {'purpose': 'register_account'}}},
        }
        retrieve_session_mock.return_value = FakeStripeSession()
        complete_pending_mock.return_value = (user, None)

        response = self.client.post(
            reverse('pages:stripe_webhook'),
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='t=1,v1=fake',
        )

        self.assertEqual(response.status_code, 200)
        post_registration_mock.assert_called_once()
        self.assertEqual(post_registration_mock.call_args.args[0], user.pk)
