# Likha — AI-Powered Waste Identification & Upcycling Guide

**Likha** is a mobile-first Django web application that turns everyday household scrap into practical DIY upcycling projects. Users snap or upload a photo of a single waste item to receive instant material classification, localized recyclability guidance, baseline Philippine junk-shop scrap estimates, and three tailored step-by-step upcycling guides with visual references.

---

## Key Features

- **Mobile-First Capture & Preprocessing:** Browser-based camera/file upload with live preview and client-side canvas downscaling, backed by server-side EXIF auto-rotation and JPEG normalization (`Pillow`).
- **Two-Tier AI Pipeline:** Decouples vision classification (Tier 1) from DIY project ideation (Tier 2) using strict Pydantic structured outputs—keeping latency low and preventing the ideation model from hallucinating unseen details.
- **Localized Recyclability & Scrap Valuation:** Maps classified materials to a deterministic table of Philippine baseline junk-shop prices (PHP/kg) so pricing is consistent and never hallucinated by the LLM.
- **Visual Upcycling Cards:** Generates three difficulty-varied DIY projects complete with tools, materials, safety-aware steps, and representative reference photos fetched concurrently across a multi-provider image fallback chain.
- **Cached Scan History:** Persists complete AI payloads as JSON so users can revisit past scans and guides instantly with zero redundant API calls.
- **User Accounts, Profiles & Themes:** Full authentication flow, validated avatar uploads, and persistent Light/Dark mode preferences.

---

## Engineering & Architecture Highlights

Built with a **vertical-slice Django architecture** (`apps/home`, `apps/login`, `apps/register`, `apps/profile`, `apps/user_settings`), Likha emphasizes resilience, cost control, and production readiness:

| Area | Implementation Details |
| :--- | :--- |
| **Fault-Tolerant AI Calls** | Automatic fallback from `GEMINI_MODEL` to `GEMINI_FALLBACK_MODEL` on retryable errors (`500`, `503`, `504`), with user-friendly HTTP error mapping (`422`, `429`, `502`, `503`, `504`). |
| **Multi-Provider Image Chain** | Queries **SerpApi (Google Images) → Pixabay → Pexels** concurrently via `ThreadPoolExecutor`, caching hits (7 days for SerpApi, 24 hours for stock providers) and misses (1 hour), with client-side thumbnail fallback on load errors. |
| **Rate Limiting & Quota Protection** | Enforces a `15 scans/hour` per-user limit via `ScanAttempt`. Unscannable photos count against abuse limits, while upstream provider outages automatically refund the user's attempt. |
| **Security Hardening** | Open-redirect protection (`url_has_allowed_host_and_scheme`) on login, `POST`-only logout and delete endpoints, strict MIME/dimension/size validation on uploads, and automatic HTTPS/HSTS/secure-cookie enforcement when `DEBUG=False`. |
| **Diagnostics & Testing** | Includes a custom `python manage.py ai_check` CLI tool to benchmark network, vision, ideation, and image providers, plus a **32-test automated suite** running on in-memory SQLite. |

---

## Tech Stack

- **Backend:** Python 3.14, Django 6.1, Pydantic v2, Pillow
- **Database:** PostgreSQL (Supabase via `dj-database-url` & `psycopg`), SQLite (in-memory test runner)
- **AI & External APIs:** Google GenAI SDK (`google-genai`), SerpApi (Google Images), Pixabay API, Pexels API
- **Frontend:** Mobile-responsive HTML5, CSS3 (custom Light/Dark theme tokens), Vanilla JavaScript
- **Production Serving:** Gunicorn, WhiteNoise (`CompressedManifestStaticFilesStorage`)

---

## Project Structure

```text
Likha/
├── config/                  # Project settings, URLs, WSGI/ASGI
├── apps/
│   ├── home/
│   │   ├── services/
│   │   │   ├── gemini.py        # Two-tier AI pipeline, schemas, & model fallback
│   │   │   ├── imaging.py       # Server-side validation, EXIF transpose, & resizing
│   │   │   ├── scrap_prices.py  # Deterministic PH baseline junk-shop price table
│   │   │   └── stock_images.py  # Concurrent multi-provider image lookup & caching
│   │   ├── management/commands/
│   │   │   └── ai_check.py      # End-to-end pipeline diagnostic & timing CLI
│   │   ├── models.py            # ScanHistory & ScanAttempt
│   │   ├── views.py             # Scanner endpoints, rate limiting, & history
│   │   └── tests.py             # Scanner, fallback, rate-limit, & image tests
│   ├── login/               # Auth views with safe ?next= validation
│   ├── register/            # Account creation
│   ├── profile/             # Profile editing & validated avatar uploads
│   └── user_settings/       # Persistent theme settings & session context processor
├── templates/               # Django HTML templates
├── static/                  # Modular CSS, JS, and brand assets
└── requirements.txt
```

---

## Database Architecture

![Likha Entity-Relationship Diagram](LIKHA_ERD.png)

- **`auth_user`:** Django's built-in authentication model.
- **`user_profiles`:** 1:1 extension storing `first_name`, `last_name`, `bio`, and `avatar_path`.
- **`user_settings`:** 1:1 preferences storing `theme` (`light`/`dark`), `language`, and `email_notifications`.
- **`scan_history`:** 1:N log per user storing `item_name`, `is_recyclable`, `scanned_at`, and the full structured response in `cached_api_data` (`JSONField`).
- **`scan_attempts`:** Indexed timestamp log (`user`, `created_at`) powering the sliding-window hourly rate limiter.

---

## Getting Started

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/neaterpoint/Likha.git
cd Likha
python -m venv .venv
```

Activate the virtual environment:
- **Windows (PowerShell):** `.\.venv\Scripts\Activate.ps1`
- **macOS / Linux:** `source .venv/bin/activate`

Install packages:

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Core Django
DEBUG=True
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=postgres://user:password@host:port/dbname

# Gemini AI
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-4-hydrogen
GEMINI_FALLBACK_MODEL=gemini-3.8-flash
GEMINI_TIMEOUT_SECONDS=75

# Reference Image Providers (optional — tried in order)
SERPAPI_API_KEY=your-serpapi-key
PIXABAY_API_KEY=your-pixabay-key
PEXELS_API_KEY=your-pexels-key
```

> **Note:** Image provider keys are optional. If none are configured, scans still complete cleanly without reference photos.

### 3. Migrate & Run

```bash
python manage.py migrate
python manage.py runserver
```

Visit `http://127.0.0.1:8000` in your browser.

---

## Testing & Diagnostics

Run the full automated test suite (uses an isolated in-memory SQLite database and mocked external APIs):

```bash
python manage.py test
```

Benchmark the live AI and image pipeline directly from the terminal:

```bash
python manage.py ai_check
python manage.py ai_check --image path/to/sample.jpg
```