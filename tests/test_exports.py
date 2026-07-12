from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from subtitle_extractor.exports import BatchResultStore, create_result_exports, safe_filename


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

    def test_batch_store_persists_each_result_before_completion(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            store = BatchResultStore(2, Path(output_dir) / "batch")
            files = store.record_success(1, "https://example.com/1", sample_result("Saved Video"))

            manifest = json.loads((store.path / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "running")
            self.assertEqual(manifest["processed"], 1)
            self.assertTrue((store.path / files["metadata"]).exists())
            self.assertTrue((store.path / files["subtitles"]).exists())

            store.record_failure(2, "https://example.com/2", "blocked")
            archive = store.complete()
            final_manifest = json.loads((store.path / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(final_manifest["status"], "completed")
            self.assertEqual(final_manifest["failed"], 1)
            self.assertIsNotNone(archive)
            self.assertTrue(archive.exists())


if __name__ == "__main__":
    unittest.main()
