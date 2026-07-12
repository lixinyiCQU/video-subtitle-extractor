from __future__ import annotations

import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_FILENAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


@dataclass(frozen=True)
class ExportArtifact:
    path: Path
    download_name: str
    media_type: str


def safe_filename(value: str | None, fallback: str = "video-subtitle") -> str:
    name = _INVALID_FILENAME.sub("_", (value or "").strip())
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = fallback
    if name.casefold() in _RESERVED_FILENAMES:
        name = f"_{name}"
    return name[:120].rstrip(" .") or fallback


def metadata_document(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": result.get("platform"),
        "extractionMethod": result.get("extractionMethod"),
        "video": result.get("video") or {},
        "selectedTrack": result.get("selectedTrack") or {},
        "availableTracks": result.get("availableTracks") or [],
        "segmentCount": len(result.get("segments") or []),
    }


def create_result_exports(results: list[dict[str, Any]]) -> list[ExportArtifact]:
    if not results:
        raise ValueError("At least one completed result is required for export.")

    output_dir = Path(tempfile.mkdtemp(prefix="subtitle-export-"))
    used_names: set[str] = set()
    files: list[ExportArtifact] = []
    for index, result in enumerate(results, start=1):
        video = result.get("video") or {}
        base_name = _unique_name(safe_filename(video.get("title"), f"video-{index}"), used_names)
        metadata_name = f"{base_name}.metadata.json"
        subtitle_name = f"{base_name}.subtitles.md"
        metadata_path = output_dir / metadata_name
        subtitle_path = output_dir / subtitle_name
        metadata_path.write_text(
            json.dumps(metadata_document(result), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        subtitle_path.write_text(str(result.get("aiContext") or ""), encoding="utf-8")
        files.extend(
            [
                ExportArtifact(metadata_path, metadata_name, "application/json"),
                ExportArtifact(subtitle_path, subtitle_name, "text/markdown"),
            ]
        )

    if len(results) == 1:
        return files

    archive_path = output_dir / "video-subtitles.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in files:
            archive.write(item.path, arcname=item.download_name)
    return [ExportArtifact(archive_path, archive_path.name, "application/zip")]


def _unique_name(base_name: str, used_names: set[str]) -> str:
    candidate = base_name
    suffix = 2
    while candidate.casefold() in used_names:
        candidate = f"{base_name} ({suffix})"
        suffix += 1
    used_names.add(candidate.casefold())
    return candidate
