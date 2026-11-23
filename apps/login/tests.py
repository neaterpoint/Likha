from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

CREDS = {"username": "vince", "password": "pw12345!"}


class LoginFlowTests(TestCase):
    def setUp(self):
        User.objects.create_user("vince", password="pw12345!")

    def test_next_is_honoured(self):
        r = self.client.post(reverse("login:login") + "?next=/scan/", CREDS)
        self.assertRedirects(r, "/scan/", fetch_redirect_response=False)

    def test_external_next_is_ignored(self):
        r = self.client.post(reverse("login:login") + "?next=https://evil.example/", CREDS)
        self.assertRedirects(r, reverse("home:home"), fetch_redirect_response=False)

    def test_logout_requires_post(self):
        self.client.login(**CREDS)
        self.assertEqual(self.client.get(reverse("login:logout")).status_code, 405)
        r = self.client.post(reverse("login:logout"))
        self.assertRedirects(r, reverse("login:login"), fetch_redirect_response=False)