from __future__ import annotations

import unittest

from subtitle_extractor.asr import (
    estimate_transcription_percent,
    language_for_asr,
    normalize_asr_device,
    normalize_asr_model,
    resolve_asr_runtime,
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


if __name__ == "__main__":
    unittest.main()
