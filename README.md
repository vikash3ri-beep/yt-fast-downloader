# YT Fast Downloader (YouTube Audio & Video Downloader)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/vikash3ri-beep/yt-fast-downloader)

**Framework:** Django 6.x (Python 3.8+)  
**Frontend:** HTML5, Tailwind CSS, Vanilla JavaScript  
**Core Engines:** `yt-dlp`, `FFmpeg`, `StreamingHttpResponse`  

---

## 🌟 Overview
**YT Fast Downloader** is a high-speed, memory-efficient web application that allows users to download YouTube videos (MP4) and extract audio (MP3) in high quality simply by pasting a YouTube URL.

### Key Capabilities
- **Fast Metadata Extraction:** Fetches video title, thumbnail, duration, view count, and available stream resolutions in < 3 seconds without downloading media upfront.
- **Split-Screen Interactive Results Card:** Modern layout displaying thumbnail with duration badge and interactive tabs for MP4 / MP3 format and resolution selection.
- **Zero Persistent Server Storage:** Files are streamed in 8KB chunks via Django's `StreamingHttpResponse` and automatically deleted from the server filesystem immediately after transmission completes.
- **FFmpeg Powered Audio:** Extracts and converts audio into 320kbps, 192kbps, or 128kbps MP3 files with proper acoustic encoding.
- **Dual Flow Architecture (MTV + Reactive AJAX):** Fully responsive, single-page reactive experience with standard Django MTV form fallback for all browsers and devices.

---

## 🏗️ Architecture Pattern (Django MTV)

```
[ Browser / Client ]
      │
      ├─► (1) URL input & validation (Tailwind UI + JS Controller)
      ▼
[ Django Views ] ───► services.py ───► [ yt-dlp Engine ]
      │                                       │
      ├─► (2) Metadata Info Fetch (JSON/HTML) ◄┘
      ▼
[ User chooses MP4/MP3 format & quality ]
      │
      ├─► (3) Streaming download request (/download/)
      ▼
[ Temporary File Storage ] ───► [ FFmpeg Converter ]
      │
      ├─► (4) 8KB Chunked StreamingHttpResponse
      ▼
[ Auto-Cleanup Generator ] ───► [ Deletes temporary file immediately ]
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python:** 3.8 or higher (Tested with Python 3.12)
- **FFmpeg:** Installed and added to system `PATH` (for audio extraction & muxing)

### 2. Installation
```powershell
# Navigate to the project directory
cd d:\projects\yt-fast-downloader

# (Optional) Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Run test suite
python manage.py test downloader

# Start development server
python manage.py runserver 127.0.0.1:8000
```

Open your browser at `http://127.0.0.1:8000/`.

---

## 🧪 Test Matrix & Quality Assurance

| Test ID | Test Case | Target | Verification |
| :--- | :--- | :--- | :--- |
| **TC-01** | Submit invalid URL (`google.com`, empty) | System rejects with 400 Bad Request and friendly warning | Passed |
| **TC-02** | Submit valid YouTube URL | System extracts metadata (title, thumbnail, duration) in < 3s | Passed |
| **TC-03** | Private or age-restricted video | System displays descriptive security/access message | Passed |
| **TC-04** | Download MP3 audio | Streams high-bitrate `.mp3` with correct `audio/mpeg` MIME header | Passed |
| **TC-05** | Download MP4 video | Streams `.mp4` video with `Content-Disposition: attachment` | Passed |
| **TC-06** | Disk Auto-Cleanup | Temporary files are guaranteed deleted after stream completion | Passed |
| **TC-07** | Responsive UI | Scalable layout with Tailwind CSS on mobile and desktop | Passed |

---

## ⚙️ Production Notes
- Use **Gunicorn** or **uWSGI** as the WSGI server.
- Use **Nginx** as reverse proxy.
- For high-concurrency environments, pair with **Celery + Redis** task queues.
