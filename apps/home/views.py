import logging
import random
import time
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import ScanAttempt, ScanHistory
from .services.gemini import AIError, NotScannable, analyze_image, analyze_text
from .services.imaging import InvalidImage, prepare_image

logger = logging.getLogger(__name__)

# Protects your Gemini quota/bill from runaway use.
# Counts every request that reaches the AI, including photos rejected as "not scannable".
MAX_SCANS_PER_HOUR = 15

def _register_attempt(user):
    """Record an AI attempt. Returns (attempt, within_limit)."""
    now = timezone.now()
    attempt = ScanAttempt.objects.create(user=user)
    recent = ScanAttempt.objects.filter(
        user=user, created_at__gte=now - timedelta(hours=1)
    ).count()
    if random.random() < 0.05:   # occasional cleanup, so it doesn't cost a query on every scan
        ScanAttempt.objects.filter(created_at__lt=now - timedelta(days=1)).delete()
    return attempt, recent <= MAX_SCANS_PER_HOUR


@login_required
def home_view(request):
    return render(request, 'home/home.html')


@login_required
def scan_page(request):
    return render(request, 'home/scan.html', {'active': 'scan'})


@login_required
@require_POST
def analyze_view(request):
    """Receives a photo, runs the two AI tiers, saves the result, returns rendered HTML."""
    started = time.monotonic()
    upload = request.FILES.get('image')
    if not upload:
        return JsonResponse({'error': 'Please choose or take a photo first.'}, status=400)

    logger.info("[scan] request from %s, upload=%d KB", request.user.username, upload.size // 1024)
    try:
        jpeg = prepare_image(upload)
    except InvalidImage as exc:
        logger.warning("[scan] rejected image: %s", exc)
        return JsonResponse({'error': str(exc)}, status=400)
    logger.info("[scan] image prepared: %d KB -> %d KB in %.2fs", upload.size // 1024, len(jpeg) // 1024, time.monotonic() - started)

    # CHANGED: _register_attempt now returns (attempt, allowed)
    attempt, allowed = _register_attempt(request.user)
    if not allowed:
        return JsonResponse(
            {'error': "You've reached the hourly scan limit. Please try again later."}, status=429
        )

    try:
        data = analyze_image(jpeg)
    except AIError as exc:
        # CHANGED: refund the attempt for provider-side failures (not for "not scannable" photos)
        if not isinstance(exc, NotScannable):
            attempt.delete()
        logger.warning("[scan] FAILED after %.1fs: %s (HTTP %s)", time.monotonic() - started, exc.message, exc.status)
        return JsonResponse({'error': exc.message}, status=exc.status)

    scan = ScanHistory.objects.create(
        user=request.user,
        item_name=data['item_name'],
        is_recyclable=data['is_recyclable'],
        cached_api_data=data,
    )
    html = render_to_string('home/_result.html', {'scan': scan, 'data': data}, request=request)
    logger.info("[scan] saved scan_id=%s, total %.1fs", scan.scan_id, time.monotonic() - started)
    return JsonResponse({'scan_id': scan.scan_id, 'html': html})


@login_required
@require_POST
def analyze_text_view(request):
    """Process a text-described item through the same quota and cached scan workflow."""
    description = (request.POST.get('item_description') or '').strip()
    if not description:
        return JsonResponse({'error': 'Describe one household waste item first.'}, status=400)
    if len(description) > 300:
        return JsonResponse({'error': 'Keep the item description to 300 characters or fewer.'}, status=400)

    attempt, allowed = _register_attempt(request.user)
    if not allowed:
        return JsonResponse(
            {'error': "You've reached the hourly scan limit. Please try again later."}, status=429
        )

    try:
        data = analyze_text(description)
    except AIError as exc:
        if not isinstance(exc, NotScannable):
            attempt.delete()
        logger.warning("[scan] text FAILED: %s (HTTP %s)", exc.message, exc.status)
        return JsonResponse({'error': exc.message}, status=exc.status)

    scan = ScanHistory.objects.create(
        user=request.user,
        item_name=data['item_name'],
        is_recyclable=data['is_recyclable'],
        cached_api_data=data,
    )
    html = render_to_string('home/_result.html', {'scan': scan, 'data': data}, request=request)
    logger.info("[scan] saved text scan_id=%s", scan.scan_id)
    return JsonResponse({'scan_id': scan.scan_id, 'html': html})


@login_required
def history_view(request):
    scans = ScanHistory.objects.filter(user=request.user).order_by('-scanned_at')
    return render(request, 'home/history.html', {'scans': scans, 'active': 'history'})


@login_required
def history_detail_view(request, scan_id):
    # Rendered from the cached JSON: no AI call needed.
    scan = get_object_or_404(ScanHistory, scan_id=scan_id, user=request.user)
    return render(request, 'home/scan_detail.html', {'scan': scan, 'data': scan.cached_api_data or {}, 'active': 'history'})


@login_required
@require_POST
def history_delete_view(request, scan_id):
    scan = get_object_or_404(ScanHistory, scan_id=scan_id, user=request.user)
    scan.delete()
    messages.success(request, 'Scan deleted.')
    return redirect('home:history')


@user_passes_test(lambda user: user.is_active and user.is_staff)
def scan_activity_view(request):
    """Give staff a private overview of scan activity and the ORM SQL behind it."""
    joined_scans = ScanHistory.objects.select_related('user').order_by('-scanned_at')

    scans_by_user = ScanHistory.objects.order_by().values('user_id')
    latest_scan = (
        ScanHistory.objects.filter(user_id=OuterRef('pk'))
        .order_by('-scanned_at', '-scan_id')
    )
    accounts_with_scans = (
        User.objects.filter(pk__in=Subquery(scans_by_user))
        .annotate(
            scan_count=Count('scans'),
            latest_scan_at=Subquery(latest_scan.values('scanned_at')[:1]),
        )
        .order_by('username')
    )

    return render(request, 'home/scan_activity.html', {
        'active': 'scan_activity',
        'scans_page': Paginator(joined_scans, 25).get_page(request.GET.get('scan_page')),
        'accounts_page': Paginator(accounts_with_scans, 25).get_page(request.GET.get('account_page')),
        'joined_scans_sql': joined_scans.query,
        'accounts_with_scans_sql': accounts_with_scans.query,
    })