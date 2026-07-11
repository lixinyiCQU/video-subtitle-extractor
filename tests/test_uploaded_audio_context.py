from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from subtitle_extractor.errors import AppError
from subtitle_extractor.gradio_ui import build_uploaded_audio_context, resolve_audio_source
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

    def test_resolve_audio_source_prefers_uploaded_file(self) -> None:
        self.assertEqual(resolve_audio_source("/tmp/uploaded.mp3", "/workspace/server.mp3"), "/tmp/uploaded.mp3")

    def test_resolve_audio_source_accepts_server_path(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".mp3", delete=False) as audio:
            audio_path = audio.name
        try:
            self.assertEqual(resolve_audio_source(None, audio_path), str(Path(audio_path)))
        finally:
            Path(audio_path).unlink(missing_ok=True)

    def test_resolve_audio_source_rejects_missing_path(self) -> None:
        with self.assertRaises(AppError):
            resolve_audio_source(None, "Z:/missing/audio.mp3")


if __name__ == "__main__":
    unittest.main()
