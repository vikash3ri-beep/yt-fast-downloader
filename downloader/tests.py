import os
from unittest.mock import patch, MagicMock
from pathlib import Path
from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings
from .services import (
    validate_youtube_url,
    format_duration,
    format_view_count,
    sanitize_filename,
    stream_file_and_cleanup,
)


class YTFastDownloaderTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_tc01_invalid_url_validation(self):
        """TC-01: Submit an invalid URL (e.g. google.com) -> Displays error message."""
        invalid_urls = [
            'google.com',
            'https://example.com/video',
            'https://vimeo.com/123456',
            'not-a-url',
            '',
        ]
        for url in invalid_urls:
            # Test service validation
            self.assertFalse(validate_youtube_url(url), f"Should fail for {url}")

            # Test results view rejection
            response = self.client.post(reverse('downloader:results'), {'url': url})
            self.assertEqual(response.status_code, 400)
            self.assertContains(response, "Please enter a valid YouTube URL.", status_code=400)

            # Test API rejection
            api_resp = self.client.post(
                reverse('downloader:api_extract'),
                data={'url': url}
            )
            self.assertEqual(api_resp.status_code, 400)
            self.assertIn('valid YouTube URL', api_resp.json().get('error', ''))

    def test_tc02_valid_url_metadata(self):
        """TC-02: Submit a valid YouTube URL -> System displays thumbnail & title."""
        valid_urls = [
            'https://www.youtube.com/watch?v=aqz-KE-bpKQ',
            'https://youtu.be/aqz-KE-bpKQ',
            'https://m.youtube.com/watch?v=aqz-KE-bpKQ',
            'https://youtube.com/shorts/aqz-KE-bpKQ',
        ]
        for url in valid_urls:
            self.assertTrue(validate_youtube_url(url), f"Should be valid for {url}")

        # Mock yt_dlp info extraction for fast testing
        mock_info = {
            'id': 'aqz-KE-bpKQ',
            'title': 'Big Buck Bunny 4K Test Video',
            'thumbnail': 'https://example.com/thumb.jpg',
            'duration': 596,
            'uploader': 'Blender Foundation',
            'view_count': 1500000,
            'formats': [{'height': 1080, 'vcodec': 'avc1'}, {'height': 720, 'vcodec': 'avc1'}],
        }

        with patch('yt_dlp.YoutubeDL') as mock_ydl_cls:
            instance = mock_ydl_cls.return_value.__enter__.return_value
            instance.extract_info.return_value = mock_info

            # Test API extraction
            resp = self.client.post(
                reverse('downloader:api_extract'),
                data={'url': 'https://www.youtube.com/watch?v=aqz-KE-bpKQ'}
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()['data']
            self.assertEqual(data['title'], 'Big Buck Bunny 4K Test Video')
            self.assertEqual(data['duration_formatted'], '09:56')
            self.assertEqual(data['channel'], 'Blender Foundation')

    def test_tc03_private_or_restricted_url(self):
        """TC-03: Submit private or restricted URL -> Displays friendly error."""
        import yt_dlp

        with patch('yt_dlp.YoutubeDL') as mock_ydl_cls:
            instance = mock_ydl_cls.return_value.__enter__.return_value
            instance.extract_info.side_effect = yt_dlp.utils.DownloadError("Private video. Sign in if you have access")

            resp = self.client.post(
                reverse('downloader:results'),
                {'url': 'https://www.youtube.com/watch?v=private_vid1'}
            )
            self.assertEqual(resp.status_code, 400)
            self.assertContains(response=resp, text="This video is private", status_code=400)

    def test_tc04_and_tc05_download_mp3_and_mp4(self):
        """TC-04 & TC-05: Download MP3 and MP4 initiated as attachment streams."""
        temp_dir = Path(settings.DOWNLOAD_TEMP_DIR)
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Test MP4
        fake_mp4 = temp_dir / "test_video.mp4"
        fake_mp4.write_bytes(b"V" * 16384)

        with patch('downloader.views.download_media_file') as mock_dl:
            mock_dl.return_value = (str(fake_mp4), "test_video.mp4", 16384)

            resp = self.client.get(reverse('downloader:download'), {
                'url': 'https://www.youtube.com/watch?v=aqz-KE-bpKQ',
                'format': 'mp4',
                'quality': '720'
            })

            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp['Content-Type'], 'video/mp4')
            self.assertIn('attachment; filename="test_video.mp4"', resp['Content-Disposition'])
            streamed_content = b"".join(resp.streaming_content)
            self.assertEqual(len(streamed_content), 16384)

        # Test MP3
        fake_mp3 = temp_dir / "test_audio.mp3"
        fake_mp3.write_bytes(b"M" * 8192)

        with patch('downloader.views.download_media_file') as mock_dl:
            mock_dl.return_value = (str(fake_mp3), "test_audio.mp3", 8192)

            resp = self.client.get(reverse('downloader:download'), {
                'url': 'https://www.youtube.com/watch?v=aqz-KE-bpKQ',
                'format': 'mp3',
                'quality': '320'
            })

            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp['Content-Type'], 'audio/mpeg')
            self.assertIn('attachment; filename="test_audio.mp3"', resp['Content-Disposition'])
            streamed_content = b"".join(resp.streaming_content)
            self.assertEqual(len(streamed_content), 8192)

    def test_tc06_auto_cleanup_after_download(self):
        """TC-06: Verify temporary files are deleted after streaming."""
        temp_dir = Path(settings.DOWNLOAD_TEMP_DIR)
        temp_dir.mkdir(parents=True, exist_ok=True)
        sample_file = temp_dir / "cleanup_test.tmp"
        sample_file.write_bytes(b"data to stream and delete")

        self.assertTrue(sample_file.exists())

        # Stream the file using stream_file_and_cleanup
        stream_gen = stream_file_and_cleanup(str(sample_file), chunk_size=4)
        chunks = list(stream_gen)
        self.assertTrue(len(chunks) > 0)

        # File must be deleted after stream completes
        self.assertFalse(sample_file.exists(), "Temporary file should have been deleted!")

    def test_tc07_homepage_renders_and_responsive(self):
        """TC-07: Home page renders successfully with responsive meta and elements."""
        resp = self.client.get(reverse('downloader:index'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'YT Fast Downloader')
        self.assertContains(resp, 'viewport')
        self.assertContains(resp, 'Get Download Links')
        self.assertContains(resp, 'Download MP4')
        self.assertContains(resp, 'Download MP3')

    def test_async_prepare_and_poll_api(self):
        """Test the asynchronous download preparation and polling endpoints."""
        with patch('downloader.views.start_async_download_job') as mock_start:
            mock_start.return_value = 'job-xyz-123'

            resp = self.client.post(
                reverse('downloader:api_prepare'),
                data={'url': 'https://www.youtube.com/watch?v=aqz-KE-bpKQ', 'format': 'mp3', 'quality': '192'}
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()['job_id'], 'job-xyz-123')

        # Test polling
        with patch('downloader.views.get_download_job_status') as mock_status:
            mock_status.return_value = {
                'status': 'downloading',
                'percent': 50.0,
                'speed': '3.2MB/s',
                'eta': '5s',
                'message': 'Downloading: 50%',
                'filename': 'video.mp3',
                'file_size': 5000,
                'error': None,
            }
            poll_resp = self.client.get(reverse('downloader:api_progress', kwargs={'job_id': 'job-xyz-123'}))
            self.assertEqual(poll_resp.status_code, 200)
            self.assertEqual(poll_resp.json()['job']['percent'], 50.0)

    def test_seo_robots_and_sitemap(self):
        """Test that robots.txt and sitemap.xml are served correctly for search engines."""
        robots_resp = self.client.get('/robots.txt')
        self.assertEqual(robots_resp.status_code, 200)
        self.assertEqual(robots_resp['Content-Type'], 'text/plain')
        self.assertContains(robots_resp, 'User-agent: *')
        self.assertContains(robots_resp, 'sitemap.xml')

        sitemap_resp = self.client.get('/sitemap.xml')
        self.assertEqual(sitemap_resp.status_code, 200)
        self.assertEqual(sitemap_resp['Content-Type'], 'application/xml')
        self.assertContains(sitemap_resp, '<urlset')

    def test_google_verification_file(self):
        """Test that any Google verification HTML file is dynamically served with required format."""
        resp = self.client.get('/google1234567890abcdef.html')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/html')
        self.assertContains(resp, 'google-site-verification: google1234567890abcdef.html')

    def test_helpers(self):
        """Test formatting and sanitization helper utilities."""
        self.assertEqual(format_duration(65), "01:05")
        self.assertEqual(format_duration(3665), "01:01:05")
        self.assertEqual(format_view_count(1500000), "1.5M views")
        self.assertEqual(format_view_count(450000), "450.0K views")
        self.assertEqual(sanitize_filename("Best Video: How-To? 2026!/\\"), "Best Video How-To 2026!")
