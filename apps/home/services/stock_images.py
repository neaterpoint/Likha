"""
Fetch one representative photo per upcycling project.

Providers are tried in this order and the first one that returns a result wins:
  1. SerpApi Google Images (SERPAPI_API_KEY)  - best match for "finished DIY project" searches
  2. Pixabay (PIXABAY_API_KEY)                - free stock photos
  3. Pexels  (PEXELS_API_KEY)                 - free stock photos

If a provider fails (quota, network, bad key) the next one is tried. With no keys at all,
projects simply show without a photo and the scan still succeeds.
"""
import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_SECONDS = 24 * 60 * 60                 # Pixabay's terms require 24h caching
SERPAPI_CACHE_SECONDS = 7 * 24 * 60 * 60     # longer, to save SerpApi credits
MISS_CACHE_SECONDS = 60 * 60                 # remember genuine "nothing found" for an hour

NO_IMAGE = {
    "image_url": None, "image_fallback_url": "",
    "image_credit": "", "image_credit_url": "", "image_source": "",
}

_STOPWORDS = {"from", "with", "the", "and", "for", "out"}


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2}


def _stock_query(query: str) -> str:
    """Stock sites do better without the leading 'DIY' that helps on Google."""
    return re.sub(r"^\s*diy\s+", "", query, flags=re.IGNORECASE)


def _serpapi(query: str):
    resp = requests.get(
        "https://serpapi.com/search.json",
        params={
            "engine": "google_images",
            "q": query[:150],
            "api_key": settings.SERPAPI_API_KEY,
            "tbs": getattr(settings, "SERPAPI_TBS", "") or "itp:photos",
            "safe": "active",
            "hl": "en",
        },
        timeout=12,
    )
    resp.raise_for_status()
    results = resp.json().get("images_results") or []

    wanted = _words(query) - _STOPWORDS
    best, best_score = None, -1
    for r in results[:15]:
        original = r.get("original") or ""
        if r.get("unsafe") or r.get("is_product"):
            continue
        if not original.startswith("https://"):
            continue
        if (r.get("original_width") or 0) < 400 or (r.get("original_height") or 0) < 250:
            continue
        score = len(wanted & _words(r.get("title")))   # prefer results whose title matches the query
        if score > best_score:                          # ties keep Google's own ranking
            best, best_score = r, score
    if not best:
        return None
    return {
        "image_url": best["original"],
        "image_fallback_url": best.get("thumbnail") or "",
        "image_credit": best.get("source") or "",
        "image_credit_url": best.get("link") or "",
        "image_source": "Google Images",
    }


def _pixabay(query: str):
    resp = requests.get(
        "https://pixabay.com/api/",
        params={
            "key": settings.PIXABAY_API_KEY,
            "q": _stock_query(query)[:100],
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
        "image_fallback_url": "",
        "image_credit": h.get("user", ""),
        "image_credit_url": h.get("pageURL", ""),
        "image_source": "Pixabay",
    }


def _pexels(query: str):
    resp = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": settings.PEXELS_API_KEY},
        params={"query": _stock_query(query), "per_page": 1, "orientation": "landscape"},
        timeout=6,
    )
    resp.raise_for_status()
    photos = resp.json().get("photos") or []
    if not photos:
        return None
    p = photos[0]
    return {
        "image_url": p["src"].get("medium") or p["src"].get("large"),
        "image_fallback_url": "",
        "image_credit": p.get("photographer", ""),
        "image_credit_url": p.get("url", ""),
        "image_source": "Pexels",
    }


def _providers():
    """Configured providers, best first."""
    chain = []
    if getattr(settings, "SERPAPI_API_KEY", ""):
        chain.append(("serpapi", _serpapi))
    if getattr(settings, "PIXABAY_API_KEY", ""):
        chain.append(("pixabay", _pixabay))
    if getattr(settings, "PEXELS_API_KEY", ""):
        chain.append(("pexels", _pexels))
    return chain


def _search_one(query: str):
    query = (query or "").strip()
    chain = _providers()
    if not query or not chain:
        return None

    digest = hashlib.sha1(query.lower().encode()).hexdigest()
    cache_key = f"stockimg:v2:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached or None

    found = None
    all_answered = True          # True only if every provider replied (so a miss is a real miss)
    for name, fn in chain:
        try:
            found = fn(query)
        except Exception:        # images are a nice-to-have; never fail a scan because of them
            all_answered = False
            logger.warning("%s image lookup failed for %r", name, query, exc_info=True)
            continue
        if found:
            break

    if found:
        ttl = SERPAPI_CACHE_SECONDS if found.get("image_source") == "Google Images" else CACHE_SECONDS
        cache.set(cache_key, found, ttl)
    elif all_answered:
        cache.set(cache_key, {}, MISS_CACHE_SECONDS)
    return found


def attach_images(projects: list) -> list:
    """Adds image_* fields to each project dict (in place)."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda p: _search_one(p.get("image_query", "")), projects))
    for project, found in zip(projects, results):
        project.update(found or NO_IMAGE)
    return projects