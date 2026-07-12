from __future__ import annotations

import io
import unittest
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient

from subtitle_extractor.jobs import JobState, _jobs, _lock
from subtitle_extractor.web import app


def result(title: str) -> dict:
    return {
        "platform": "bilibili",
        "extractionMethod": "subtitle",
        "video": {"title": title},
        "selectedTrack": {},
        "availableTracks": [],
        "segments": [],
        "aiContext": f"# {title}",
    }


class WebExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def tearDown(self) -> None:
        with _lock:
            _jobs.pop("test-export", None)

    def test_selected_video_metadata_export_uses_title(self) -> None:
        with _lock:
            _jobs["test-export"] = JobState(
                id="test-export",
                status="completed",
                result={"items": [{"status": "completed", "result": result("Title One")}], "total": 1},
            )

        response = self.client.get("/api/jobs/test-export/export?kind=metadata&item=0")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Title%20One.metadata.json", response.headers["content-disposition"])
        self.assertEqual(response.json()["video"]["title"], "Title One")

    def test_batch_bundle_is_a_zip(self) -> None:
        with _lock:
            _jobs["test-export"] = JobState(
                id="test-export",
                status="completed",
                result={
                    "items": [
                        {"status": "completed", "result": result("First")},
                        {"status": "completed", "result": result("Second")},
                    ],
                    "total": 2,
                },
            )

        response = self.client.get("/api/jobs/test-export/export?kind=bundle")

        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertIn("First.metadata.json", archive.namelist())
            self.assertIn("Second.subtitles.md", archive.namelist())

    def test_batch_endpoint_detects_platform_and_keeps_cookies_separate(self) -> None:
        with patch("subtitle_extractor.web.create_batch_extract_job") as create_job:
            create_job.return_value = JobState(id="mixed-job")
            response = self.client.post(
                "/api/extract/batch/start",
                data={
                    "urls": (
                        "https://www.bilibili.com/video/BV1abc\n"
                        "https://www.youtube.com/watch?v=abc"
                    ),
                    "bilibili_cookie_text": "SESSDATA=bili",
                    "youtube_cookie_text": "SID=youtube",
                },
            )

        self.assertEqual(response.status_code, 200)
        requests, cookie_inputs = create_job.call_args.args
        self.assertEqual([request.platform for request in requests], ["bilibili", "youtube"])
        self.assertEqual(cookie_inputs["bilibili"].header, "SESSDATA=bili")
        self.assertEqual(cookie_inputs["youtube"].header, "SID=youtube")

    def test_local_ui_uses_auto_detection_and_two_cookie_sections(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('id="platform"', response.text)
        self.assertIn('name="bilibili_cookie_text"', response.text)
        self.assertIn('name="youtube_cookie_text"', response.text)


if __name__ == "__main__":
    unittest.main()
