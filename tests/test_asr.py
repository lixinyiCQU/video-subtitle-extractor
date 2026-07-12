from __future__ import annotations

import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from subtitle_extractor.asr import (
    estimate_transcription_percent,
    language_for_asr,
    normalize_asr_device,
    normalize_asr_model,
    resolve_asr_runtime,
    transcribe_audio,
)
from subtitle_extractor.errors import AppError


class AsrTests(unittest.TestCase):
    def test_language_mapping(self) -> None:
        self.assertIsNone(language_for_asr("auto"))
        self.assertEqual(language_for_asr("zh-Hans"), "zh")
        self.assertEqual(language_for_asr("en"), "en")
        self.assertEqual(language_for_asr("ja"), "ja")

    def test_model_validation(self) -> None:
        self.assertEqual(normalize_asr_model("base"), "base")
        with self.assertRaises(AppError):
            normalize_asr_model("not-a-model")

    def test_device_validation(self) -> None:
        self.assertEqual(normalize_asr_device("AUTO"), "auto")
        self.assertEqual(normalize_asr_device("cpu"), "cpu")
        with self.assertRaises(AppError):
            normalize_asr_device("mps")

    def test_cpu_runtime(self) -> None:
        self.assertEqual(resolve_asr_runtime("cpu"), ("cpu", "int8"))

    def test_transcription_progress_estimate(self) -> None:
        self.assertEqual(estimate_transcription_percent(0, 0), 75)
        self.assertEqual(estimate_transcription_percent(50, 100), 82)
        self.assertEqual(estimate_transcription_percent(200, 100), 89)

    def test_model_is_unloaded_after_transcription(self) -> None:
        backend = SimpleNamespace(unloaded=False)

        def unload_model() -> None:
            backend.unloaded = True

        backend.unload_model = unload_model

        class FakeWhisperModel:
            def __init__(self, *_args, **_kwargs) -> None:
                self.model = backend

            def transcribe(self, *_args, **_kwargs):
                segments = [SimpleNamespace(start=0.0, end=1.0, text=" hello ")]
                return iter(segments), SimpleNamespace(duration=1.0)

        fake_module = ModuleType("faster_whisper")
        fake_module.WhisperModel = FakeWhisperModel
        with (
            patch.dict("sys.modules", {"faster_whisper": fake_module}),
            patch("subtitle_extractor.asr.log_resource_snapshot"),
        ):
            result = transcribe_audio(Path("sample.wav"), "en", "base", device_name="cpu")

        self.assertEqual(result[0].text, "hello")
        self.assertTrue(backend.unloaded)


if __name__ == "__main__":
    unittest.main()
