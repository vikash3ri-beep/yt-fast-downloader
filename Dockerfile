FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system FFmpeg and Node.js (required for fast yt-dlp & MP3 conversion)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . /app/
RUN python manage.py migrate --no-input

EXPOSE 8000
CMD ["gunicorn", "yt_downloader.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
