import os
import re
import uuid
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Any, Generator, Optional
from django.conf import settings
import yt_dlp

logger = logging.getLogger(__name__)

# Standard YouTube URL regex matching youtube.com (watch, shorts, embed, v) and youtu.be
YOUTUBE_URL_REGEX = re.compile(
    r'^(https?://)?(www\.|m\.)?(youtube\.com/(watch\?(.*&)?v=|embed/|v/|shorts/)|youtu\.be/)([\w-]{11})(\S*)?$',
    re.IGNORECASE
)

# In-memory storage for active download preparation jobs
DOWNLOAD_JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def validate_youtube_url(url: str) -> bool:
    """Validate if the provided string is a valid YouTube video or shorts URL."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    return bool(YOUTUBE_URL_REGEX.match(url))


def format_duration(seconds: Optional[int]) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if not seconds or seconds < 0:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_view_count(views: Optional[int]) -> str:
    """Format view count into readable short format (e.g., 1.2M, 450K)."""
    if not views:
        return "0 views"
    if views >= 1_000_000_000:
        return f"{views / 1_000_000_000:.1f}B views"
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M views"
    if views >= 1_000:
        return f"{views / 1_000:.1f}K views"
    return f"{views:,} views"


def sanitize_filename(name: str) -> str:
    """Sanitize title for safe filesystem and HTTP header naming."""
    clean = re.sub(r'[\\/*?:"<>|]', '', name)
    clean = clean.strip()
    return clean[:80] if clean else "youtube_download"


def get_video_metadata(url: str) -> Dict[str, Any]:
    """
    Extract metadata (title, thumbnail, duration, author, resolutions) using yt-dlp.
    Fast execution with skip_download=True and Node.js runtime.
    """
    url = url.strip()
    if not validate_youtube_url(url):
        raise ValueError("Please enter a valid YouTube URL.")

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'socket_timeout': 15,
        'extract_flat': False,
        'js_runtimes': {'node': {}},
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError("Could not retrieve video information. Please try again.")

            thumbnail = info.get('thumbnail')
            if not thumbnail and info.get('thumbnails'):
                thumbnail = info['thumbnails'][-1].get('url')

            duration_raw = info.get('duration', 0)
            duration_formatted = format_duration(duration_raw)

            # Available video heights
            formats = info.get('formats', [])
            resolutions = set()
            for f in formats:
                h = f.get('height')
                vcodec = f.get('vcodec')
                if h and vcodec != 'none':
                    resolutions.add(h)

            sorted_res = sorted([r for r in resolutions if r in [360, 480, 720, 1080, 1440, 2160]], reverse=True)
            if not sorted_res:
                sorted_res = [720, 360]

            return {
                'url': url,
                'id': info.get('id', ''),
                'title': info.get('title', 'YouTube Media'),
                'thumbnail': thumbnail or 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=80',
                'duration': duration_raw,
                'duration_formatted': duration_formatted,
                'channel': info.get('uploader') or info.get('channel') or 'YouTube Creator',
                'views': format_view_count(info.get('view_count')),
                'views_raw': info.get('view_count', 0),
                'available_resolutions': sorted_res,
                'description': (info.get('description') or '')[:200],
            }

    except yt_dlp.utils.DownloadError as e:
        error_str = str(e).lower()
        if 'private video' in error_str:
            raise ValueError("This video is private and cannot be accessed.")
        elif 'age' in error_str or 'sign in' in error_str:
            raise ValueError("This video is age-restricted or requires account verification.")
        elif 'not available' in error_str or 'removed' in error_str:
            raise ValueError("This video is not available or has been removed.")
        elif 'live event' in error_str or 'is currently live' in error_str:
            raise ValueError("Live streams cannot be downloaded while in progress.")
        else:
            raise ValueError(f"Failed to access video: {str(e)[:120]}")
    except Exception as e:
        logger.exception("Unexpected error in get_video_metadata")
        raise ValueError(f"An unexpected error occurred: {str(e)}")


def build_ydl_options(outtmpl: str, media_format: str, quality: Optional[str] = None, progress_hook=None) -> tuple[dict, str]:
    """
    Build robust yt-dlp options compatible with local FFmpeg (avoiding AV1 codec issues).
    """
    media_format = media_format.lower()
    if media_format not in ['mp4', 'mp3']:
        media_format = 'mp4'

    ydl_opts = {
        'outtmpl': outtmpl,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'js_runtimes': {'node': {}},
        'socket_timeout': 30,
    }

    if progress_hook:
        ydl_opts['progress_hooks'] = [progress_hook]

    if media_format == 'mp3':
        audio_bitrate = quality if quality in ['128', '192', '256', '320'] else '192'
        ydl_opts.update({
            # Prefer m4a/aac audio stream or bestaudio
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': audio_bitrate,
                'nopostoverwrites': False,
            }],
        })
        final_ext = 'mp3'
    else:
        # For MP4: Target H.264 (avc1) or progressive MP4 to avoid AV1/VP9 FFmpeg issues
        h_filter = f"[height<={quality}]" if quality and quality.isdigit() else ""
        format_selector = (
            f"bestvideo[vcodec^=avc1]{h_filter}[ext=mp4]+bestaudio[ext=m4a]/"
            f"best[vcodec^=avc1]{h_filter}[ext=mp4]/"
            f"best{h_filter}[ext=mp4]/"
            f"bestvideo[vcodec^=avc1]{h_filter}+bestaudio/"
            f"best{h_filter}/best"
        )
        ydl_opts.update({
            'format': format_selector,
            'merge_output_format': 'mp4',
        })
        final_ext = 'mp4'

    return ydl_opts, final_ext


def download_media_file(url: str, media_format: str = 'mp4', quality: Optional[str] = None) -> tuple[str, str, int]:
    """
    Direct synchronous download for standard MTV requests.
    Returns (file_path, display_filename, file_size).
    """
    if not validate_youtube_url(url):
        raise ValueError("Please enter a valid YouTube URL.")

    temp_dir = Path(settings.DOWNLOAD_TEMP_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_uuid = str(uuid.uuid4())

    title_sanitized = "youtube_download"
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True, 'noplaylist': True, 'js_runtimes': {'node': {}}}) as ydl:
            meta = ydl.extract_info(url, download=False)
            if meta and meta.get('title'):
                title_sanitized = sanitize_filename(meta['title'])
    except Exception:
        pass

    outtmpl = str(temp_dir / f"{file_uuid}.%(ext)s")
    ydl_opts, final_ext = build_ydl_options(outtmpl, media_format, quality)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        logger.exception("yt-dlp download failed")
        raise ValueError(f"Download failed: {str(e)[:140]}")

    target_pattern = f"{file_uuid}.*"
    matching_files = list(temp_dir.glob(target_pattern))

    if not matching_files:
        raise FileNotFoundError("Downloaded media file could not be found on server.")

    chosen_file = matching_files[0]
    for f in matching_files:
        if f.suffix.lower() == f".{final_ext}":
            chosen_file = f
            break

    file_size = chosen_file.stat().st_size
    display_filename = f"{title_sanitized}.{final_ext}"

    return str(chosen_file), display_filename, file_size


def start_async_download_job(url: str, media_format: str = 'mp4', quality: Optional[str] = None) -> str:
    """
    Start an asynchronous download job with live progress tracking.
    Returns job_id.
    """
    if not validate_youtube_url(url):
        raise ValueError("Please enter a valid YouTube URL.")

    job_id = str(uuid.uuid4())
    temp_dir = Path(settings.DOWNLOAD_TEMP_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)

    with JOBS_LOCK:
        DOWNLOAD_JOBS[job_id] = {
            'status': 'starting',
            'percent': 0,
            'speed': '',
            'eta': '',
            'message': 'Connecting to YouTube servers...',
            'file_path': None,
            'filename': None,
            'file_size': 0,
            'error': None,
            'created_at': time.time(),
        }

    thread = threading.Thread(
        target=_run_download_job_worker,
        args=(job_id, url, media_format, quality),
        daemon=True
    )
    thread.start()

    return job_id


def _run_download_job_worker(job_id: str, url: str, media_format: str, quality: Optional[str]):
    """Background worker executing yt-dlp and reporting live progress."""
    temp_dir = Path(settings.DOWNLOAD_TEMP_DIR)
    file_uuid = str(uuid.uuid4())
    outtmpl = str(temp_dir / f"{file_uuid}.%(ext)s")

    title_sanitized = "youtube_download"
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True, 'noplaylist': True, 'js_runtimes': {'node': {}}}) as ydl:
            meta = ydl.extract_info(url, download=False)
            if meta and meta.get('title'):
                title_sanitized = sanitize_filename(meta['title'])
    except Exception:
        pass

    def progress_hook(d):
        if d['status'] == 'downloading':
            p_str = d.get('_percent_str', '0%').replace('%', '').strip()
            try:
                percent = float(p_str)
            except ValueError:
                percent = 0.0

            speed = d.get('_speed_str', '').strip()
            eta = d.get('_eta_str', '').strip()
            downloaded = d.get('_downloaded_bytes_str', '').strip()
            total = d.get('_total_bytes_str') or d.get('_total_bytes_estimate_str') or ''

            with JOBS_LOCK:
                if job_id in DOWNLOAD_JOBS:
                    DOWNLOAD_JOBS[job_id]['status'] = 'downloading'
                    DOWNLOAD_JOBS[job_id]['percent'] = percent
                    DOWNLOAD_JOBS[job_id]['speed'] = speed
                    DOWNLOAD_JOBS[job_id]['eta'] = eta
                    msg = f"Downloading: {percent:.1f}%"
                    if speed:
                        msg += f" ({speed})"
                    if eta:
                        msg += f" - ETA: {eta}"
                    DOWNLOAD_JOBS[job_id]['message'] = msg

        elif d['status'] == 'finished':
            with JOBS_LOCK:
                if job_id in DOWNLOAD_JOBS:
                    DOWNLOAD_JOBS[job_id]['status'] = 'processing'
                    DOWNLOAD_JOBS[job_id]['percent'] = 98.0
                    action_msg = "Extracting MP3 audio with FFmpeg..." if media_format == 'mp3' else "Merging video streams with FFmpeg..."
                    DOWNLOAD_JOBS[job_id]['message'] = action_msg

    ydl_opts, final_ext = build_ydl_options(outtmpl, media_format, quality, progress_hook)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        target_pattern = f"{file_uuid}.*"
        matching_files = list(temp_dir.glob(target_pattern))

        if not matching_files:
            raise FileNotFoundError("Downloaded media file could not be found.")

        chosen_file = matching_files[0]
        for f in matching_files:
            if f.suffix.lower() == f".{final_ext}":
                chosen_file = f
                break

        file_size = chosen_file.stat().st_size
        display_filename = f"{title_sanitized}.{final_ext}"

        with JOBS_LOCK:
            if job_id in DOWNLOAD_JOBS:
                DOWNLOAD_JOBS[job_id]['status'] = 'ready'
                DOWNLOAD_JOBS[job_id]['percent'] = 100.0
                DOWNLOAD_JOBS[job_id]['file_path'] = str(chosen_file)
                DOWNLOAD_JOBS[job_id]['filename'] = display_filename
                DOWNLOAD_JOBS[job_id]['file_size'] = file_size
                DOWNLOAD_JOBS[job_id]['message'] = 'Ready! Initiating file download...'

    except Exception as e:
        logger.exception(f"Async download job failed for {job_id}")
        with JOBS_LOCK:
            if job_id in DOWNLOAD_JOBS:
                DOWNLOAD_JOBS[job_id]['status'] = 'error'
                DOWNLOAD_JOBS[job_id]['error'] = f"Download failed: {str(e)[:140]}"
                DOWNLOAD_JOBS[job_id]['message'] = f"Download failed: {str(e)[:140]}"


def get_download_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get the current progress status of a background job."""
    with JOBS_LOCK:
        job = DOWNLOAD_JOBS.get(job_id)
        if not job:
            return None
        return {
            'status': job['status'],
            'percent': job['percent'],
            'speed': job['speed'],
            'eta': job['eta'],
            'message': job['message'],
            'filename': job.get('filename'),
            'file_size': job.get('file_size', 0),
            'error': job.get('error'),
        }


def get_completed_job_file(job_id: str) -> Optional[tuple[str, str, int]]:
    """Retrieve and pop the completed job file details."""
    with JOBS_LOCK:
        job = DOWNLOAD_JOBS.get(job_id)
        if not job or job['status'] != 'ready' or not job['file_path']:
            return None
        return job['file_path'], job['filename'], job['file_size']


def stream_file_and_cleanup(file_path: str, chunk_size: int = 8192) -> Generator[bytes, None, None]:
    """
    Generator that streams the file in 8KB chunks and deletes the temporary file
    once transmission ends or in case of client disconnection.
    """
    try:
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Temporary file cleaned up: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file {file_path}: {e}")
