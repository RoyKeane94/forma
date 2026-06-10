from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Profile


class AccountsSiteSmokeTests(TestCase):
    def _create_user(self, username: str):
        User = get_user_model()
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass1234",
        )

    def test_public_account_pages_render(self):
        urls = [
            reverse("accounts:login"),
            reverse("accounts:register"),
            reverse("accounts:waitlist"),
            reverse("accounts:logged_out"),
            reverse("accounts:account_deleted"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_register_checkout_success_without_session_redirects(self):
        response = self.client.get(reverse("accounts:register_checkout_success"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:register"))

    def test_private_account_pages_require_login(self):
        urls = [
            reverse("accounts:register_name"),
            reverse("accounts:password_change"),
            reverse("accounts:cancel_subscription"),
            reverse("accounts:delete_account"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response.url)

    def test_private_account_pages_render_for_logged_in_user(self):
        user = self._create_user("account_member")
        Profile.objects.get_or_create(user=user)
        self.client.login(username="account_member", password="pass1234")

        urls = [
            reverse("accounts:register_name"),
            reverse("accounts:password_change"),
            reverse("accounts:delete_account"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

        cancel_response = self.client.get(reverse("accounts:cancel_subscription"))
        self.assertEqual(cancel_response.status_code, 302)
