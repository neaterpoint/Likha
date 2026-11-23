import io
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import Profile


def png_upload(name="a.png"):
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "green").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class ProfileFormTests(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)

        self.user = User.objects.create_user("vince", password="pw12345!")
        self.client.login(username="vince", password="pw12345!")
        self.url = reverse("profile:profile")

    def test_valid_save_with_avatar(self):
        r = self.client.post(self.url, {"first_name": "Ana", "last_name": "Cruz", "bio": "Hi", "avatar_path": png_upload()})
        self.assertEqual(r.status_code, 302)
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.first_name, "Ana")
        self.assertTrue(profile.avatar_path)

    def test_overlong_name_is_rejected_not_a_500(self):
        r = self.client.post(self.url, {"first_name": "x" * 60, "last_name": "", "bio": ""})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "field-error")
        self.assertFalse(Profile.objects.get(user=self.user).first_name)

    def test_non_image_upload_is_rejected(self):
        fake = SimpleUploadedFile("evil.jpg", b"definitely not an image", content_type="image/jpeg")
        r = self.client.post(self.url, {"first_name": "Ana", "last_name": "", "bio": "", "avatar_path": fake})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Profile.objects.get(user=self.user).avatar_path)