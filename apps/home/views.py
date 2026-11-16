import logging
import time
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import ScanHistory
from .services.gemini import AIError, analyze_image
from .services.imaging import InvalidImage, prepare_image

logger = logging.getLogger(__name__)

# Protects your Gemini quota/bill from runaway use.
MAX_SCANS_PER_HOUR = 15


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

    recent = ScanHistory.objects.filter(
        user=request.user, scanned_at__gte=timezone.now() - timedelta(hours=1)
    ).count()
    if recent >= MAX_SCANS_PER_HOUR:
        return JsonResponse(
            {'error': "You've reached the hourly scan limit. Please try again later."}, status=429
        )

    logger.info("[scan] request from %s, upload=%d KB", request.user.username, upload.size // 1024)
    try:
        jpeg = prepare_image(upload)
    except InvalidImage as exc:
        logger.warning("[scan] rejected image: %s", exc)
        return JsonResponse({'error': str(exc)}, status=400)
    logger.info("[scan] image prepared: %d KB -> %d KB in %.2fs", upload.size // 1024, len(jpeg) // 1024, time.monotonic() - started)

    try:
        data = analyze_image(jpeg)
    except AIError as exc:
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
