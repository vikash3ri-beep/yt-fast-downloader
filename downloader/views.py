import json
import logging
from urllib.parse import quote
from django.shortcuts import render, redirect
from django.http import StreamingHttpResponse, JsonResponse, HttpResponseBadRequest, Http404
from django.views.decorators.http import require_http_methods
from .services import (
    validate_youtube_url,
    get_video_metadata,
    download_media_file,
    start_async_download_job,
    get_download_job_status,
    get_completed_job_file,
    stream_file_and_cleanup,
)

logger = logging.getLogger(__name__)


def index_view(request):
    """Render the homepage."""
    context = {
        'page_title': 'YT Fast Downloader - Download YouTube Videos & Audio Free',
    }
    return render(request, 'index.html', context)


@require_http_methods(["GET", "POST"])
def results_view(request):
    """
    Standard MTV Results Page:
    Accepts URL from form submission, extracts metadata, and renders results.html.
    """
    url = ""
    if request.method == "POST":
        url = request.POST.get("url", "").strip()
    else:
        url = request.GET.get("url", "").strip()

    if not url:
        if request.method == "POST":
            return render(request, 'index.html', {
                'error_message': 'Please enter a valid YouTube URL.',
                'input_url': '',
            }, status=400)
        return redirect('downloader:index')

    if not validate_youtube_url(url):
        return render(request, 'index.html', {
            'error_message': 'Please enter a valid YouTube URL.',
            'input_url': url,
        }, status=400)

    try:
        metadata = get_video_metadata(url)
        return render(request, 'results.html', {
            'video': metadata,
            'page_title': f"{metadata['title']} - YT Fast Downloader",
        })
    except ValueError as e:
        return render(request, 'index.html', {
            'error_message': str(e),
            'input_url': url,
        }, status=400)
    except Exception as e:
        logger.exception("Error in results_view")
        return render(request, 'index.html', {
            'error_message': f"Failed to retrieve video details: {str(e)}",
            'input_url': url,
        }, status=500)


@require_http_methods(["POST"])
def api_extract_info(request):
    """
    JSON API endpoint for modern dynamic metadata extraction without page reloads.
    """
    url = ""
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            url = data.get('url', '').strip()
        else:
            url = request.POST.get('url', '').strip()
    except Exception:
        url = request.POST.get('url', '').strip()

    if not url or not validate_youtube_url(url):
        return JsonResponse({
            'success': False,
            'error': 'Please enter a valid YouTube URL.',
        }, status=400)

    try:
        metadata = get_video_metadata(url)
        return JsonResponse({
            'success': True,
            'data': metadata,
        })
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=400)
    except Exception as e:
        logger.exception("API metadata extraction error")
        return JsonResponse({
            'success': False,
            'error': 'Unable to fetch video information. Please verify the URL or try again later.',
        }, status=500)


@require_http_methods(["POST"])
def api_prepare_download(request):
    """
    Start background download preparation with live progress tracking.
    """
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            url = data.get('url', '').strip()
            media_format = data.get('format', 'mp4').strip().lower()
            quality = data.get('quality', '')
        else:
            url = request.POST.get('url', '').strip()
            media_format = request.POST.get('format', 'mp4').strip().lower()
            quality = request.POST.get('quality', '')
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid request parameters.'}, status=400)

    if not url or not validate_youtube_url(url):
        return JsonResponse({'success': False, 'error': 'Please enter a valid YouTube URL.'}, status=400)

    if media_format not in ['mp4', 'mp3']:
        media_format = 'mp4'

    # Sanitize quality input based on format
    if media_format == 'mp3':
        quality = quality if quality in ['128', '192', '256', '320'] else '192'
    else:
        quality = quality if quality and quality.isdigit() else '720'

    try:
        job_id = start_async_download_job(url, media_format, quality)
        return JsonResponse({'success': True, 'job_id': job_id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_download_progress(request, job_id):
    """
    Poll live progress for an active download job.
    """
    status = get_download_job_status(job_id)
    if not status:
        return JsonResponse({'success': False, 'error': 'Job not found or expired.'}, status=404)

    return JsonResponse({
        'success': True,
        'job': status,
        'download_url': f"/download-ready/{job_id}/" if status['status'] == 'ready' else None,
    })


@require_http_methods(["GET"])
def download_ready_view(request, job_id):
    """
    Instantly stream the pre-downloaded and converted media file, then auto-delete it.
    """
    file_info = get_completed_job_file(job_id)
    if not file_info:
        raise Http404("Download file expired or not ready.")

    file_path, display_filename, file_size = file_info
    media_format = 'mp3' if display_filename.endswith('.mp3') else 'mp4'
    content_type = 'audio/mpeg' if media_format == 'mp3' else 'video/mp4'

    response = StreamingHttpResponse(
        stream_file_and_cleanup(file_path, chunk_size=8192),
        content_type=content_type,
    )
    encoded_filename = quote(display_filename)
    safe_ascii_filename = display_filename.encode('ascii', 'ignore').decode('ascii') or f"download.{media_format}"
    response['Content-Disposition'] = f'attachment; filename="{safe_ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}'
    response['Content-Length'] = str(file_size)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@require_http_methods(["GET", "POST"])
def download_view(request):
    """
    Direct synchronous download stream fallback.
    """
    if request.method == "POST":
        url = request.POST.get('url', '').strip()
        media_format = request.POST.get('format', 'mp4').strip().lower()
        quality = request.POST.get('quality', '')
    else:
        url = request.GET.get('url', '').strip()
        media_format = request.GET.get('format', 'mp4').strip().lower()
        quality = request.GET.get('quality', '')

    if not url:
        return HttpResponseBadRequest("Missing video URL.")

    if not validate_youtube_url(url):
        return HttpResponseBadRequest("Invalid YouTube URL.")

    if media_format not in ['mp4', 'mp3']:
        media_format = 'mp4'

    if media_format == 'mp3':
        quality = quality if quality in ['128', '192', '256', '320'] else '192'

    try:
        file_path, display_filename, file_size = download_media_file(
            url=url,
            media_format=media_format,
            quality=quality if quality else None
        )

        content_type = 'video/mp4' if media_format == 'mp4' else 'audio/mpeg'
        response = StreamingHttpResponse(
            stream_file_and_cleanup(file_path, chunk_size=8192),
            content_type=content_type,
        )

        encoded_filename = quote(display_filename)
        safe_ascii_filename = display_filename.encode('ascii', 'ignore').decode('ascii') or f"download.{media_format}"
        response['Content-Disposition'] = f'attachment; filename="{safe_ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}'
        response['Content-Length'] = str(file_size)
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    except ValueError as e:
        return render(request, 'index.html', {
            'error_message': str(e),
            'input_url': url,
        }, status=400)
    except Exception as e:
        logger.exception("Direct download view error")
        return render(request, 'index.html', {
            'error_message': f"Download failed: {str(e)}",
            'input_url': url,
        }, status=500)
