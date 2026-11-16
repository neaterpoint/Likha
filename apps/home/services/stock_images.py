"""
Fetch one representative stock photo per upcycling project.

Providers (first one with a key wins):
  - Pixabay  (PIXABAY_API_KEY)  free key, instant: pixabay.com/api/docs
  - Pexels   (PEXELS_API_KEY)   works only if you already have a key (new keys are paused)

With no key set, projects simply show without a photo.
Results are cached for 24 hours (also required by Pixabay's API terms).
"""
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_SECONDS = 24 * 60 * 60
NO_IMAGE = {"image_url": None, "image_credit": "", "image_credit_url": "", "image_source": ""}


def _pixabay(query: str):
    resp = requests.get(
        "https://pixabay.com/api/",
        params={
            "key": settings.PIXABAY_API_KEY,
            "q": query[:100],
            "image_type": "photo",
            "orientation": "horizontal",
            "safesearch": "true",
            "per_page": 3,   # Pixabay's minimum
        },
        timeout=6,
    )
    resp.raise_for_status()
    hits = resp.json().get("hits") or []
    if not hits:
        return None
    h = hits[0]
    return {
        "image_url": h.get("webformatURL"),
        "image_credit": h.get("user", ""),
        "image_credit_url": h.get("pageURL", ""),
        "image_source": "Pixabay",
    }


def _pexels(query: str):
    resp = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": settings.PEXELS_API_KEY},
        params={"query": query, "per_page": 1, "orientation": "landscape"},
        timeout=6,
    )
    resp.raise_for_status()
    photos = resp.json().get("photos") or []
    if not photos:
        return None
    p = photos[0]
    return {
        "image_url": p["src"].get("medium") or p["src"].get("large"),
        "image_credit": p.get("photographer", ""),
        "image_credit_url": p.get("url", ""),
        "image_source": "Pexels",
    }


def _provider():
    if getattr(settings, "PIXABAY_API_KEY", ""):
        return "pixabay", _pixabay
    if getattr(settings, "PEXELS_API_KEY", ""):
        return "pexels", _pexels
    return None, None


def _search_one(query: str):
    name, fn = _provider()
    if not fn or not query:
        return None
    digest = hashlib.sha1(query.lower().strip().encode()).hexdigest()
    cache_key = f"stockimg:{name}:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached or None
    try:
        found = fn(query)
    except Exception:  # images are a nice-to-have; never fail a scan because of them
        logger.warning("%s image lookup failed for %r", name, query, exc_info=True)
        return None
    cache.set(cache_key, found or {}, CACHE_SECONDS)
    return found


def attach_images(projects: list) -> list:
    """Adds image_* fields to each project dict (in place)."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda p: _search_one(p.get("image_query", "")), projects))
    for project, found in zip(projects, results):
        project.update(found or NO_IMAGE)
    return projects
