from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from subtitle_extractor.gradio_ui import build_cookie_input


class GradioUiTests(unittest.TestCase):
    def test_raw_cookie_header_is_not_written_to_file(self) -> None:
        cookie_input = build_cookie_input("Cookie: SID=abc; X=1", None)

        self.assertEqual(cookie_input.header, "SID=abc; X=1")
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
