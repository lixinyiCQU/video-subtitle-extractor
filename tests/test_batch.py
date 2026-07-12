from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from subtitle_extractor.batch import extract_batch_context, parse_video_urls
from subtitle_extractor.errors import AppError
from subtitle_extractor.exports import BatchResultStore
from subtitle_extractor.models import CookieInput, ExtractRequest


def request(url: str) -> ExtractRequest:
    return ExtractRequest(url=url, platform="youtube", language="auto", browser="none")


class BatchTests(unittest.TestCase):
    def test_parse_urls_accepts_lines_and_commas(self) -> None:
        self.assertEqual(
            parse_video_urls("https://a.example/1\nhttps://a.example/2, https://a.example/3"),
            [
                "https://a.example/1",
                "https://a.example/2",
                "https://a.example/3",
            ],
        )

    def test_partial_failure_does_not_discard_successful_result(self) -> None:
        progress: list[tuple[str, int]] = []

        def extract(item: ExtractRequest, _cookies: CookieInput, progress=None) -> dict:
            if item.url.endswith("2"):
                raise AppError("blocked", status_code=502)
            if progress:
                progress("Done", 100)
            return {"video": {"title": item.url}}

        with tempfile.TemporaryDirectory() as output_dir:
            store = BatchResultStore(2, Path(output_dir) / "batch")
            with patch("subtitle_extractor.batch.extract_subtitle_context", side_effect=extract):
                batch = extract_batch_context(
                    [request("https://a.example/1"), request("https://a.example/2")],
                    CookieInput(),
                    progress=lambda message, percent: progress.append((message, percent)),
                    result_store=store,
                )

            self.assertEqual(batch["completed"], 1)
            self.assertEqual(batch["failed"], 1)
            self.assertEqual(batch["items"][0]["status"], "completed")
            self.assertEqual(batch["items"][1]["error"], "blocked")
            self.assertTrue((store.path / "manifest.json").exists())
            self.assertTrue((store.path / "batch-results.zip").exists())
            self.assertIn(("Video 1/2: Done", 50), progress)


if __name__ == "__main__":
    unittest.main()
