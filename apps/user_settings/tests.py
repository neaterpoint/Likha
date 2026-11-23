from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class ThemeTests(TestCase):
    def setUp(self):
        User.objects.create_user("vince", password="pw12345!")
        self.client.login(username="vince", password="pw12345!")

    def test_defaults_to_light(self):
        self.assertContains(self.client.get(reverse("home:home")), 'data-theme="light"')

    def test_dark_mode_applies_after_saving_and_can_be_switched_off(self):
        url = reverse("user_settings:settings")
        self.client.post(url, {"dark_mode": "on"})
        self.assertContains(self.client.get(reverse("home:home")), 'data-theme="dark"')
        self.client.post(url, {})
        self.assertContains(self.client.get(reverse("home:home")), 'data-theme="light"')