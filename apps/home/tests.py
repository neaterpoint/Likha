import io
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import ScanHistory
from .services import gemini
from .services.gemini import Classification, Ideas, Project


def fake_jpeg(size=(200, 100)):
    buf = io.BytesIO()
    Image.new("RGB", size, "green").save(buf, "JPEG")
    return SimpleUploadedFile("p.jpg", buf.getvalue(), content_type="image/jpeg")


def fake_generate(contents, schema, system_instruction, level, label=""):
    if schema is Classification:
        return Classification(
            is_scannable_item=True, item_name="plastic water bottle", material="plastic_pet",
            is_recyclable=True, recyclability_note="Rinse and flatten.", confidence="high",
        )
    return Ideas(projects=[
        Project(title=f"Idea {i}", difficulty="Easy", time_estimate="30 minutes", tools=["scissors"],
                materials_needed=["bottle"], steps=["Cut", "Decorate"], image_query="bottle planter")
        for i in range(3)
    ])


class ScannerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("vince", password="pw12345!")
        self.client.login(username="vince", password="pw12345!")

    def test_login_required(self):
        self.client.logout()
        r = self.client.post(reverse("home:analyze"), {"image": fake_jpeg()})
        self.assertEqual(r.status_code, 302)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(reverse("home:analyze")).status_code, 405)

    def test_missing_image(self):
        r = self.client.post(reverse("home:analyze"))
        self.assertEqual(r.status_code, 400)

    def test_not_an_image(self):
        bad = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
        r = self.client.post(reverse("home:analyze"), {"image": bad})
        self.assertEqual(r.status_code, 400)

    @patch.object(gemini, "_generate", side_effect=fake_generate)
    def test_full_scan_saves_and_renders(self, _):
        r = self.client.post(reverse("home:analyze"), {"image": fake_jpeg()})
        self.assertEqual(r.status_code, 200, r.content)
        scan = ScanHistory.objects.get()
        self.assertEqual(scan.user, self.user)
        self.assertTrue(scan.is_recyclable)
        self.assertEqual(len(scan.cached_api_data["projects"]), 3)
        self.assertEqual(scan.cached_api_data["scrap_value"]["unit"], "PHP/kg")
        self.assertIn("Idea 0", r.json()["html"])

    @patch.object(gemini, "_generate")
    def test_not_scannable(self, gen):
        gen.return_value = Classification(
            is_scannable_item=False, item_name="person", material="other",
            is_recyclable=False, recyclability_note="", confidence="low",
        )
        r = self.client.post(reverse("home:analyze"), {"image": fake_jpeg()})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(ScanHistory.objects.count(), 0)

    @patch.object(gemini, "_generate", side_effect=gemini.AIBusy("busy"))
    def test_ai_busy(self, _):
        r = self.client.post(reverse("home:analyze"), {"image": fake_jpeg()})
        self.assertEqual(r.status_code, 429)

    @patch.object(gemini, "_generate", side_effect=fake_generate)
    def test_history_detail_uses_cache_and_is_private(self, gen):
        self.client.post(reverse("home:analyze"), {"image": fake_jpeg()})
        scan = ScanHistory.objects.get()
        gen.reset_mock()
        r = self.client.get(reverse("home:history_detail", args=[scan.scan_id]))
        self.assertContains(r, "Idea 1")
        gen.assert_not_called()              # no AI call when viewing history
        User.objects.create_user("other", password="pw12345!")
        self.client.login(username="other", password="pw12345!")
        self.assertEqual(self.client.get(reverse("home:history_detail", args=[scan.scan_id])).status_code, 404)

    def test_delete_requires_post_and_owner(self):
        scan = ScanHistory.objects.create(user=self.user, item_name="can", cached_api_data={})
        url = reverse("home:history_delete", args=[scan.scan_id])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.assertEqual(ScanHistory.objects.count(), 0)

    def test_hourly_limit(self):
        for _ in range(15):
            ScanHistory.objects.create(user=self.user, item_name="x", cached_api_data={})
        r = self.client.post(reverse("home:analyze"), {"image": fake_jpeg()})
        self.assertEqual(r.status_code, 429)

    @override_settings(GEMINI_API_KEY="")
    def test_missing_key(self):
        gemini._client = None
        r = self.client.post(reverse("home:analyze"), {"image": fake_jpeg()})
        self.assertEqual(r.status_code, 503)


class StockImageTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    @override_settings(PIXABAY_API_KEY="k", PEXELS_API_KEY="")
    def test_pixabay_lookup_and_cache(self):
        from .services import stock_images
        resp = patch("apps.home.services.stock_images.requests.get")
        with resp as get:
            get.return_value.json.return_value = {"hits": [
                {"webformatURL": "https://x/y.jpg", "user": "ann", "pageURL": "https://pixabay.com/p/1"}]}
            projects = [{"image_query": "bottle planter"}, {"image_query": "bottle planter"}]
            stock_images.attach_images(projects)
            self.assertEqual(projects[0]["image_url"], "https://x/y.jpg")
            self.assertEqual(projects[0]["image_source"], "Pixabay")
            stock_images.attach_images([{"image_query": "bottle planter"}])
            self.assertLessEqual(get.call_count, 2)   # second call served from cache

    @override_settings(PIXABAY_API_KEY="", PEXELS_API_KEY="")
    def test_no_key_means_no_image_but_no_error(self):
        from .services import stock_images
        projects = [{"image_query": "x"}]
        stock_images.attach_images(projects)
        self.assertIsNone(projects[0]["image_url"])

    @override_settings(PIXABAY_API_KEY="k")
    def test_api_failure_is_swallowed(self):
        from .services import stock_images
        with patch("apps.home.services.stock_images.requests.get", side_effect=Exception("boom")):
            projects = [{"image_query": "x"}]
            stock_images.attach_images(projects)
        self.assertIsNone(projects[0]["image_url"])


class FallbackTests(TestCase):
    def _client(self, *effects):
        from unittest.mock import MagicMock
        c = MagicMock()
        c.models.generate_content.side_effect = list(effects)
        return c

    def _ok(self):
        from unittest.mock import MagicMock
        return MagicMock(parsed=None, text='{"projects": []}')

    @override_settings(GEMINI_MODEL="main", GEMINI_FALLBACK_MODEL="backup")
    def test_timeout_falls_back_to_second_model(self):
        from google.genai import errors as ge
        c = self._client(ge.ServerError(504, {"error": {"message": "deadline"}}), self._ok())
        with patch.object(gemini, "_get_client", return_value=c):
            result = gemini._generate("hi", Ideas, "sys", "LOW")
        self.assertEqual(result.projects, [])
        models = [call.kwargs["model"] for call in c.models.generate_content.call_args_list]
        self.assertEqual(models, ["main", "backup"])

    @override_settings(GEMINI_MODEL="main", GEMINI_FALLBACK_MODEL="backup")
    def test_both_models_time_out_gives_friendly_504(self):
        from google.genai import errors as ge
        e = ge.ServerError(504, {"error": {"message": "deadline"}})
        c = self._client(e, e)
        with patch.object(gemini, "_get_client", return_value=c):
            with self.assertRaises(gemini.AITimeout):
                gemini._generate("hi", Ideas, "sys", "LOW")

    @override_settings(GEMINI_MODEL="main", GEMINI_FALLBACK_MODEL="backup")
    def test_bad_key_does_not_fall_back(self):
        from google.genai import errors as ge
        c = self._client(ge.ClientError(403, {"error": {"message": "nope"}}))
        with patch.object(gemini, "_get_client", return_value=c):
            with self.assertRaises(gemini.AINotConfigured):
                gemini._generate("hi", Ideas, "sys", "LOW")
        self.assertEqual(c.models.generate_content.call_count, 1)


class PageRenderTests(TestCase):
    def setUp(self):
        User.objects.create_user("vince", password="pw12345!")
        self.client.login(username="vince", password="pw12345!")

    def test_pages_render_with_shared_design(self):
        for name in ("home:home", "home:scan", "home:history"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 200, name)
            self.assertContains(r, "css/home/home.css")
            self.assertContains(r, 'class="topbar"')
        self.assertContains(self.client.get(reverse("home:scan")), "css/home/scan.css")

    def test_active_nav_marker(self):
        self.assertContains(self.client.get(reverse("home:scan")), 'href="/scan/" class="active"')
        self.assertContains(self.client.get(reverse("home:history")), 'href="/history/" class="active"')


class AICheckCommandTests(TestCase):
    @override_settings(GEMINI_API_KEY="k", GEMINI_MODEL="main", GEMINI_FALLBACK_MODEL="")
    def test_command_runs_and_reports(self):
        from io import StringIO
        from unittest.mock import MagicMock
        from django.core.management import call_command
        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = MagicMock(
            text="OK", parsed=Ideas(projects=[]))
        out = StringIO()
        with patch("apps.home.management.commands.ai_check.genai.Client", return_value=fake_client), \
             patch("apps.home.management.commands.ai_check.requests.get") as get:
            get.return_value.status_code = 404
            call_command("ai_check", stdout=out)
        text = out.getvalue()
        self.assertIn("== 1. Network ==", text)
        self.assertIn("OK", text)
        self.assertIn("(skip) vision step", text)
