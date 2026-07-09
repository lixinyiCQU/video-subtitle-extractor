from __future__ import annotations

import unittest

from subtitle_extractor.asr import language_for_asr, normalize_asr_model
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


if __name__ == "__main__":
    unittest.main()
