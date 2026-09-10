FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

# Install system FFmpeg and Node.js for high-speed yt-dlp & MP3 conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/
RUN python manage.py collectstatic --no-input
RUN python manage.py migrate --no-input

EXPOSE 8000
CMD exec gunicorn yt_downloader.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --timeout 180
