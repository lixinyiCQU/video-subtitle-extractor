from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yt_dlp.utils import DownloadError

from subtitle_extractor.service import map_download_error
from subtitle_extractor.ytdlp_client import download_audio, extract_video_info


class FakeYoutubeDL:
    calls = 0
    options: list[dict] = []

    def __init__(self, options: dict) -> None:
        self.options.append(options)
        self.output_path = Path(options["outtmpl"].replace("%(id)s", "video").replace("%(ext)s", "m4a"))

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def extract_info(self, _url: str, download: bool) -> dict:
        self.__class__.calls += 1
        if self.calls == 1:
            raise DownloadError("Read timed out")
        self.output_path.write_bytes(b"audio")
        return {"id": "video", "ext": "m4a"}

    def prepare_filename(self, _info: dict) -> str:
        return str(self.output_path)


class FakeMetadataYoutubeDL:
    calls = 0

    def __init__(self, options: dict) -> None:
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def extract_info(self, _url: str, download: bool) -> dict:
        self.__class__.calls += 1
        if self.calls == 1:
            raise DownloadError("Remote end closed connection without response")
        return {"id": "video", "title": "Recovered"}


class DownloadResilienceTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeYoutubeDL.calls = 0
        FakeYoutubeDL.options = []

    def test_transient_timeout_refreshes_media_url_and_retries(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            with (
                patch("subtitle_extractor.ytdlp_client.YoutubeDL", FakeYoutubeDL),
                patch("subtitle_extractor.ytdlp_client.time.sleep"),
            ):
                path = download_audio(
                    "https://www.bilibili.com/video/BV1test",
                    "bilibili",
                    None,
                    None,
                    None,
                    output_dir,
                )

        self.assertEqual(FakeYoutubeDL.calls, 2)
        self.assertEqual(path.name, "video.m4a")
        self.assertEqual(FakeYoutubeDL.options[0]["http_chunk_size"], 512 * 1024)
        self.assertEqual(FakeYoutubeDL.options[0]["socket_timeout"], 45)
        self.assertEqual(FakeYoutubeDL.options[0]["retry_sleep_functions"]["http"](n=2), 2)

    def test_timeout_error_is_clean_and_specific(self) -> None:
        error = DownloadError("\x1b[0;31mERROR:\x1b[0m Read timed out")

        mapped = map_download_error(error, "bilibili")

        self.assertEqual(mapped.status_code, 504)
        self.assertIn("media CDN timed out", mapped.message)
        self.assertNotIn("\x1b", mapped.message)

    def test_metadata_transient_disconnect_is_retried(self) -> None:
        FakeMetadataYoutubeDL.calls = 0
        with (
            patch("subtitle_extractor.ytdlp_client.YoutubeDL", FakeMetadataYoutubeDL),
            patch("subtitle_extractor.ytdlp_client.time.sleep"),
        ):
            info = extract_video_info("https://example.com/video", "bilibili", None, None, None)

        self.assertEqual(info["title"], "Recovered")
        self.assertEqual(FakeMetadataYoutubeDL.calls, 2)


if __name__ == "__main__":
    unittest.main()
