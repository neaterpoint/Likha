"""
Diagnose the AI pipeline from the terminal.

    python manage.py ai_check
    python manage.py ai_check --image C:\\path\\to\\photo.jpg

Prints OK/FAIL and seconds for every step, so you can see exactly where the
slowness or the error comes from (network, key, model, image step, ideas step, Pixabay).
"""
import io
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image

from apps.home.services.gemini import (
    CLASSIFY_SYSTEM, IDEATE_SYSTEM, Classification, Ideas,
)
from apps.home.services.imaging import prepare_image


class _Upload(io.BytesIO):
    """Minimal stand-in for an uploaded file (prepare_image needs .size)."""
    @property
    def size(self):
        return len(self.getvalue())


class Command(BaseCommand):
    help = "Time each step of the Gemini + Pixabay pipeline and show where it fails."

    def add_arguments(self, parser):
        parser.add_argument("--image", help="Path to a photo to run the real vision step on.")
        parser.add_argument("--timeout", type=int, default=90, help="Per-call timeout in seconds (default 90).")

    # ---------- helpers ----------
    def _step(self, label, fn):
        started = time.monotonic()
        try:
            detail = fn()
            self.stdout.write(self.style.SUCCESS(f"  OK    {time.monotonic() - started:5.1f}s  {label}") + (f"  -> {detail}" if detail else ""))
            return True
        except genai_errors.APIError as exc:
            self.stdout.write(self.style.ERROR(f"  FAIL  {time.monotonic() - started:5.1f}s  {label}  -> HTTP {getattr(exc, 'code', '?')}: {str(exc)[:200]}"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  FAIL  {time.monotonic() - started:5.1f}s  {label}  -> {type(exc).__name__}: {str(exc)[:200]}"))
        return False

    def _gen(self, client, model, contents, level, system=None, schema=None):
        cfg = dict(thinking_config=types.ThinkingConfig(thinking_level=level))
        if system:
            cfg["system_instruction"] = system
        if schema:
            cfg["response_mime_type"] = "application/json"
            cfg["response_schema"] = schema
        r = client.models.generate_content(model=model, contents=contents, config=types.GenerateContentConfig(**cfg))
        return r

    # ---------- main ----------
    def handle(self, *args, **opts):
        out = self.stdout.write
        key = settings.GEMINI_API_KEY
        models = [settings.GEMINI_MODEL]
        fb = getattr(settings, "GEMINI_FALLBACK_MODEL", "")
        if fb and fb != settings.GEMINI_MODEL:
            models.append(fb)

        out("\n== Config ==")
        out(f"  main model     : {settings.GEMINI_MODEL}")
        out(f"  fallback model : {fb or '(none)'}")
        out(f"  app timeout    : {getattr(settings, 'GEMINI_TIMEOUT_SECONDS', 75)}s   (this check uses {opts['timeout']}s)")
        out(f"  GEMINI_API_KEY : {'set (' + str(len(key)) + ' chars)' if key else 'MISSING'}")
        out(f"  PIXABAY key    : {'set' if getattr(settings, 'PIXABAY_API_KEY', '') else 'not set (images skipped)'}")
        if not key:
            self.stdout.write(self.style.ERROR("Set GEMINI_API_KEY in .env first."))
            return

        out("\n== 1. Network ==")
        def reach():
            r = requests.get("https://generativelanguage.googleapis.com/", timeout=15)
            return f"HTTP {r.status_code} (any response means the network path works)"
        self._step("reach generativelanguage.googleapis.com", reach)

        client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=opts["timeout"] * 1000))

        for model in models:
            out(f"\n== 2. Model: {model} ==")
            self._step("tiny text prompt (LOW)", lambda: self._gen(client, model, "Reply with the single word OK.", "LOW").text.strip()[:40])
            self._step("ideas step: structured JSON, text only (LOW)", lambda: (
                f"{len(self._gen(client, model, 'Item: plastic water bottle\nMain material: Plastic (PET bottles)\n\nSuggest exactly 3 different upcycling projects for this item.', 'LOW', IDEATE_SYSTEM, Ideas).parsed.projects)} projects"
            ))
            self._step("ideas step: structured JSON, text only (MEDIUM)", lambda: (
                f"{len(self._gen(client, model, 'Item: plastic water bottle\nMain material: Plastic (PET bottles)\n\nSuggest exactly 3 different upcycling projects for this item.', 'MEDIUM', IDEATE_SYSTEM, Ideas).parsed.projects)} projects"
            ))
            if opts["image"]:
                def vision():
                    with open(opts["image"], "rb") as fh:
                        jpeg = prepare_image(_Upload(fh.read()))
                    r = self._gen(client, model,
                                  [types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), "Identify this item and the material it is mainly made of."],
                                  "LOW", CLASSIFY_SYSTEM, Classification)
                    c = r.parsed
                    return f"{c.item_name!r}, {c.material}, recyclable={c.is_recyclable} (image sent: {len(jpeg)//1024} KB)"
                self._step("vision step with your photo (LOW)", vision)
            else:
                out("  (skip) vision step: pass --image path\\to\\photo.jpg to test it")

        out("\n== 3. Pixabay ==")
        if getattr(settings, "PIXABAY_API_KEY", ""):
            def pix():
                r = requests.get("https://pixabay.com/api/", params={"key": settings.PIXABAY_API_KEY, "q": "bottle planter", "per_page": 3}, timeout=10)
                r.raise_for_status()
                return f"{len(r.json().get('hits', []))} hits"
            self._step("search 'bottle planter'", pix)
        else:
            out("  (skip) no PIXABAY_API_KEY")

        out("\nHow to read this: if the tiny text prompt is slow, it's the network/model. If only the structured/MEDIUM/vision steps are slow, "
            "it's output size or thinking. A FAIL with HTTP 401/403 is the key; 429 is quota; 504 is the model taking too long.\n")
