from __future__ import annotations

import io
import unittest
import zipfile

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


if __name__ == "__main__":
    unittest.main()
