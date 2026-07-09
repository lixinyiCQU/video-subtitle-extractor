from __future__ import annotations

import unittest

from subtitle_extractor.jobs import JobState, job_to_dict


class JobTests(unittest.TestCase):
    def test_job_to_dict(self) -> None:
        job = JobState(id="abc", status="running", message="Working", percent=42)
        payload = job_to_dict(job)

        self.assertEqual(payload["id"], "abc")
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["percent"], 42)


if __name__ == "__main__":
    unittest.main()
