from __future__ import annotations

import json
import shutil
import unittest
import zipfile

from subtitle_extractor.exports import create_result_exports, safe_filename


def sample_result(title: str) -> dict:
    return {
        "platform": "youtube",
        "extractionMethod": "subtitle",
        "video": {"title": title, "url": "https://example.com/video", "duration": 12},
        "selectedTrack": {"language": "en", "source": "manual", "ext": "vtt", "name": "English"},
        "availableTracks": [],
        "segments": [{"text": "Hello"}],
        "aiContext": f"# {title}\n\nHello",
    }


class ExportTests(unittest.TestCase):
    def test_safe_filename_handles_windows_characters_and_reserved_names(self) -> None:
        self.assertEqual(safe_filename('A/B:C*D?"E<F>G|'), "A_B_C_D__E_F_G_")
        self.assertEqual(safe_filename("CON"), "_CON")

    def test_single_result_creates_title_based_metadata_and_subtitle_files(self) -> None:
        artifacts = create_result_exports([sample_result("Demo Video")])
        try:
            self.assertEqual(
                [artifact.download_name for artifact in artifacts],
                ["Demo Video.metadata.json", "Demo Video.subtitles.md"],
            )
            metadata = json.loads(artifacts[0].path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["video"]["title"], "Demo Video")
            self.assertEqual(metadata["segmentCount"], 1)
        finally:
            shutil.rmtree(artifacts[0].path.parent, ignore_errors=True)

    def test_multiple_results_create_zip_and_disambiguate_duplicate_titles(self) -> None:
        artifacts = create_result_exports([sample_result("Same"), sample_result("Same")])
        try:
            self.assertEqual(len(artifacts), 1)
            self.assertEqual(artifacts[0].download_name, "video-subtitles.zip")
            with zipfile.ZipFile(artifacts[0].path) as archive:
                self.assertEqual(
                    archive.namelist(),
                    [
                        "Same.metadata.json",
                        "Same.subtitles.md",
                        "Same (2).metadata.json",
                        "Same (2).subtitles.md",
                    ],
                )
        finally:
            shutil.rmtree(artifacts[0].path.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
