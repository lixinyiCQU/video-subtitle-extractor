from __future__ import annotations

import unittest

from subtitle_extractor.errors import AppError
from subtitle_extractor.validation import detect_platform, ensure_supported_url, normalize_platform
from subtitle_extractor.ytdlp_client import choose_track, collect_tracks, ydl_options


class ValidationAndTrackTests(unittest.TestCase):
    def test_platform_validation(self) -> None:
        self.assertEqual(normalize_platform("YouTube"), "youtube")
        with self.assertRaises(AppError):
            normalize_platform("vimeo")

    def test_url_validation(self) -> None:
        self.assertEqual(
            ensure_supported_url("https://www.youtube.com/watch?v=abc", "youtube"),
            "https://www.youtube.com/watch?v=abc",
        )
        with self.assertRaises(AppError):
            ensure_supported_url("https://www.youtube.com/watch?v=abc", "bilibili")

    def test_platform_is_detected_from_url(self) -> None:
        self.assertEqual(detect_platform("https://www.bilibili.com/video/BV1abc"), "bilibili")
        self.assertEqual(detect_platform("https://b23.tv/example"), "bilibili")
        self.assertEqual(detect_platform("https://www.youtube.com/watch?v=abc"), "youtube")
        self.assertEqual(detect_platform("https://youtu.be/abc"), "youtube")
        self.assertEqual(detect_platform("https://www.youtube.com:443/watch?v=abc"), "youtube")
        with self.assertRaises(AppError):
            detect_platform("https://fakeyoutube.com/watch?v=abc")

    def test_collect_tracks_filters_danmaku_and_prefers_chinese(self) -> None:
        info = {
            "subtitles": {
                "danmaku": [{"ext": "xml", "url": "https://example.com/comment.xml"}],
                "en": [{"ext": "vtt", "url": "https://example.com/en.vtt"}],
                "zh-Hans": [{"ext": "srt", "data": "1\n00:00:00,000 --> 00:00:01,000\nhi"}],
            },
            "automatic_captions": {},
        }

        tracks = collect_tracks(info)
        selected = choose_track(tracks, "auto")

        self.assertEqual(len(tracks), 2)
        self.assertEqual(selected["language"], "zh-Hans")
        self.assertEqual(selected["ext"], "srt")

    def test_metadata_options_ignore_missing_formats(self) -> None:
        options = ydl_options(platform="youtube")

        self.assertTrue(options["ignore_no_formats_error"])
        self.assertTrue(options["noplaylist"])
        self.assertEqual(options["socket_timeout"], 45)
        self.assertEqual(options["retries"], 8)


if __name__ == "__main__":
    unittest.main()
