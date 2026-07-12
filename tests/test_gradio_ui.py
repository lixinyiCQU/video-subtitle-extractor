from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from subtitle_extractor.gradio_ui import (
    batch_result_choices,
    build_cookie_input,
    parse_video_urls,
    view_batch_result,
)


class GradioUiTests(unittest.TestCase):
    def test_batch_urls_support_lines_and_commas(self) -> None:
        self.assertEqual(
            parse_video_urls("https://a.example/1\nhttps://a.example/2, https://a.example/3"),
            [
                "https://a.example/1",
                "https://a.example/2",
                "https://a.example/3",
            ],
        )

    def test_batch_selector_only_contains_completed_results(self) -> None:
        result = {
            "platform": "youtube",
            "extractionMethod": "subtitle",
            "video": {"title": "Successful video"},
            "selectedTrack": {},
            "segments": [],
            "aiContext": "context",
            "plainText": "plain",
        }
        items = [
            {"status": "failed", "error": "blocked", "result": None},
            {"status": "completed", "error": None, "result": result},
        ]

        self.assertEqual(batch_result_choices(items), [("Successful video", "0")])
        metadata, context, plain = view_batch_result("0", items)
        self.assertIn("Successful video", metadata)
        self.assertEqual(context, "context")
        self.assertEqual(plain, "plain")

    def test_raw_cookie_header_is_not_written_to_file(self) -> None:
        cookie_input = build_cookie_input("Cookie: SID=abc; X=1", None)

        self.assertEqual(cookie_input.header, "SID=abc; X=1")
        self.assertIsNone(cookie_input.path)

    def test_extension_exported_cookie_pairs_are_treated_as_header(self) -> None:
        cookie_input = build_cookie_input("SID=abc; HSID=def; VISITOR_INFO1_LIVE=ghi", None)

        self.assertEqual(cookie_input.header, "SID=abc; HSID=def; VISITOR_INFO1_LIVE=ghi")
        self.assertIsNone(cookie_input.path)

    def test_netscape_cookie_text_uses_temp_file(self) -> None:
        raw = "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tSID\tabc"
        cookie_input = build_cookie_input(raw, None)
        try:
            self.assertIsNotNone(cookie_input.path)
            self.assertIsNone(cookie_input.header)
        finally:
            cookie_input.cleanup()

    def test_uploaded_cookie_file_is_copied_to_request_temp_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as source:
            source.write("# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tSID\tabc")
            source_path = source.name

        cookie_input = build_cookie_input(None, source_path)
        try:
            self.assertIsNotNone(cookie_input.path)
            self.assertNotEqual(cookie_input.path, source_path)
        finally:
            cookie_input.cleanup()
            Path(source_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
