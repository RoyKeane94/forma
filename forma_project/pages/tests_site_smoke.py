from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ProfilePageView, ProfileScrollEvent, TrainerProfile


class SiteSmokeTests(TestCase):
    def _create_user(self, username: str, *, is_superuser: bool = False):
        User = get_user_model()
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass1234",
        )
        if is_superuser:
            user.is_superuser = True
            user.is_staff = True
            user.save(update_fields=["is_superuser", "is_staff"])
        return user

    def _create_profile(
        self,
        *,
        user,
        forma_made: bool = False,
        is_published: bool = True,
        completed: bool = True,
        first_name: str = "Agi",
        last_name: str = "Alexander",
        created_by=None,
    ) -> TrainerProfile:
        return TrainerProfile.objects.create(
            user=user,
            first_name=first_name,
            last_name=last_name,
            tagline="Trainer",
            bio="Bio",
            forma_made=forma_made,
            is_published=is_published,
            completed_at=timezone.now() if completed else None,
            created_by=created_by,
        )

    def test_public_pages_render(self):
        owner = self._create_user("public_profile_owner")
        profile = self._create_profile(user=owner, forma_made=False, is_published=True, completed=True)

        urls = [
            reverse("home"),
            reverse("pages:privacy"),
            reverse("pages:terms"),
            reverse("pages:profile_enquiry"),
            reverse("pages:trainer_profile", kwargs={"profile_slug": profile.slug}),
            reverse("pages:trainer_profile_proof", kwargs={"profile_slug": profile.slug}),
            reverse("pages:trainer_proof_submit", kwargs={"profile_slug": profile.slug}),
            reverse("pages:trainer_proof_submit_success", kwargs={"profile_slug": profile.slug}),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_forma_keyed_urls_render_for_forma_profiles(self):
        staff = self._create_user("forma_creator", is_superuser=True)
        profile_owner = self._create_user("forma_profile_owner")
        profile = self._create_profile(
            user=profile_owner,
            forma_made=True,
            is_published=True,
            completed=False,
            first_name="Forma",
            last_name="Made",
            created_by=staff,
        )

        urls = [
            reverse(
                "pages:trainer_profile_forma",
                kwargs={"profile_slug": profile.slug, "url_key": profile.public_url_key},
            ),
            reverse(
                "pages:trainer_profile_forma_proof",
                kwargs={"profile_slug": profile.slug, "url_key": profile.public_url_key},
            ),
            reverse(
                "pages:keep_forma_profile",
                kwargs={"profile_slug": profile.slug, "url_key": profile.public_url_key},
            ),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_authenticated_pages_require_login(self):
        urls = [
            reverse("pages:my_account"),
            reverse("pages:proof_notifications"),
            reverse("pages:proof_testimonials_page"),
            reverse("pages:proof_testimonials_edit"),
            reverse("pages:onboarding"),
            reverse("pages:onboarding_edit"),
            reverse("pages:onboarding_step", kwargs={"step": 1}),
            reverse("pages:onboarding_step_edit", kwargs={"step": 1}),
            reverse("pages:onboarding_complete"),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response.url)

    def test_authenticated_pages_render_for_logged_in_user(self):
        user = self._create_user("member")
        self._create_profile(user=user, forma_made=False, is_published=True, completed=False)
        self.client.login(username="member", password="pass1234")

        onboarding_redirect = self.client.get(reverse("pages:onboarding"))
        self.assertEqual(onboarding_redirect.status_code, 302)

        urls = [
            reverse("pages:my_account"),
            reverse("pages:proof_notifications"),
            reverse("pages:proof_testimonials_page"),
            reverse("pages:proof_testimonials_edit"),
            reverse("pages:onboarding_step", kwargs={"step": 1}),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_staff_pages_require_superuser(self):
        staff_candidate = self._create_user("not_staff")
        owner = self._create_user("forma_profile_subject")
        profile = self._create_profile(
            user=owner,
            forma_made=True,
            is_published=True,
            completed=False,
            created_by=staff_candidate,
        )

        self.client.login(username="not_staff", password="pass1234")

        get_urls = [
            reverse("pages:staff_forma_profiles"),
            reverse("pages:staff_forma_profile_new"),
            reverse("pages:staff_forma_profile_new_yaml"),
            reverse("pages:staff_forma_onboarding", kwargs={"profile_pk": profile.pk}),
            reverse("pages:staff_forma_onboarding_step", kwargs={"profile_pk": profile.pk, "step": 1}),
            reverse("pages:staff_forma_onboarding_edit", kwargs={"profile_pk": profile.pk}),
            reverse("pages:staff_forma_onboarding_step_edit", kwargs={"profile_pk": profile.pk, "step": 1}),
        ]

        for url in get_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response.url)

    def test_staff_pages_and_actions_work_for_superuser(self):
        staff = self._create_user("staff_owner", is_superuser=True)
        profile_owner = self._create_user("staff_subject")
        profile = self._create_profile(
            user=profile_owner,
            forma_made=True,
            is_published=True,
            completed=False,
            created_by=staff,
        )

        self.client.login(username="staff_owner", password="pass1234")

        get_urls = [
            reverse("pages:staff_forma_profiles"),
            reverse("pages:staff_forma_profile_new"),
            reverse("pages:staff_forma_profile_new_yaml"),
            reverse("pages:staff_forma_onboarding", kwargs={"profile_pk": profile.pk}),
            reverse("pages:staff_forma_onboarding_step", kwargs={"profile_pk": profile.pk, "step": 1}),
            reverse("pages:staff_forma_onboarding_edit", kwargs={"profile_pk": profile.pk}),
            reverse("pages:staff_forma_onboarding_step_edit", kwargs={"profile_pk": profile.pk, "step": 1}),
        ]

        for url in get_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn(response.status_code, {200, 302})

        response = self.client.post(reverse("pages:staff_forma_profile_reset_analytics"))
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            reverse("pages:staff_forma_outreach_toggle", kwargs={"profile_pk": profile.pk}),
            data={"field": "email_1", "checked": "1"},
        )
        self.assertEqual(response.status_code, 204)

    def test_analytics_endpoints_accept_valid_payloads(self):
        page = "/agi-alexander/"
        response = self.client.post(reverse("pages:track_profile_pageview"), data={"page": page})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(ProfilePageView.objects.count(), 1)

        response = self.client.post(reverse("pages:track_profile_scroll"), data={"page": page, "depth": "50"})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(ProfileScrollEvent.objects.count(), 1)

    def test_analytics_endpoints_ignore_invalid_payloads(self):
        response = self.client.post(reverse("pages:track_profile_pageview"), data={"page": ""})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(ProfilePageView.objects.count(), 0)

        response = self.client.post(reverse("pages:track_profile_scroll"), data={"page": "/bad/", "depth": "99"})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(ProfileScrollEvent.objects.count(), 0)

    @override_settings(STRIPE_WEBHOOK_SECRET="")
    def test_webhook_returns_404_when_not_configured(self):
        response = self.client.post(reverse("pages:stripe_webhook"), data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 404)

    def test_keep_profile_checkout_success_requires_session_id(self):
        response = self.client.get(reverse("pages:keep_forma_profile_success"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("pages:my_account"))

    def test_legacy_profile_id_route_redirects_to_slug(self):
        owner = self._create_user("legacy_profile_owner")
        profile = self._create_profile(user=owner, forma_made=False, is_published=True, completed=True)
        response = self.client.get(reverse("pages:trainer_profile_legacy", kwargs={"profile_id": profile.pk}))
        self.assertEqual(response.status_code, 301)
        self.assertIn(f"/{profile.slug}/", response.url)
