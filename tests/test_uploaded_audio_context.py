from __future__ import annotations

import unittest

from subtitle_extractor.gradio_ui import build_uploaded_audio_context
from subtitle_extractor.models import Segment


class UploadedAudioContextTests(unittest.TestCase):
    def test_context_contains_uploaded_audio_metadata_and_timeline(self) -> None:
        metadata, ai_context, plain_text = build_uploaded_audio_context(
            "/tmp/example.mp3",
            "zh",
            "base",
            "cuda",
            [
                Segment(start=0, end=1.2, text="First line."),
                Segment(start=1.2, end=2.5, text="Second line."),
            ],
        )

        self.assertIn("uploaded-audio", metadata)
        self.assertIn("example.mp3", ai_context)
        self.assertIn("[00:00:00 - 00:00:01]", ai_context)
        self.assertEqual(plain_text, "First line.\n\nSecond line.")


if __name__ == "__main__":
    unittest.main()
