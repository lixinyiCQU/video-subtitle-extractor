from __future__ import annotations

import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import PROJECT_ROOT


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


class BatchResultStore:
    def __init__(self, total: int, root: str | Path | None = None) -> None:
        timestamp = datetime.now(timezone.utc)
        self.batch_id = f"{timestamp.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        self.created_at = timestamp.isoformat()
        self.total = total
        self.path = Path(root) if root else PROJECT_ROOT / "results" / self.batch_id
        self.path.mkdir(parents=True, exist_ok=False)
        self.items: list[dict[str, Any]] = []
        self.used_names: set[str] = set()
        self._write_manifest("running")
        print(f"[subtitle-extractor][results] batch-directory={self.path}", flush=True)

    def record_success(self, index: int, url: str, result: dict[str, Any]) -> dict[str, str]:
        video = result.get("video") or {}
        base_name = _unique_name(safe_filename(video.get("title"), f"video-{index}"), self.used_names)
        metadata_name = f"{base_name}.metadata.json"
        subtitle_name = f"{base_name}.subtitles.md"
        _atomic_write_text(
            self.path / metadata_name,
            json.dumps(metadata_document(result), ensure_ascii=False, indent=2),
        )
        _atomic_write_text(self.path / subtitle_name, str(result.get("aiContext") or ""))
        files = {"metadata": metadata_name, "subtitles": subtitle_name}
        self.items.append(
            {
                "index": index,
                "url": url,
                "status": "completed",
                "title": video.get("title"),
                "files": files,
                "error": None,
            }
        )
        self._write_manifest("running")
        print(
            f"[subtitle-extractor][results] saved item={index}/{self.total} title={base_name}",
            flush=True,
        )
        return files

    def record_failure(self, index: int, url: str, error: str) -> None:
        self.items.append(
            {
                "index": index,
                "url": url,
                "status": "failed",
                "title": None,
                "files": {},
                "error": error,
            }
        )
        self._write_manifest("running")

    def complete(self) -> Path | None:
        completed = sum(item["status"] == "completed" for item in self.items)
        self._write_manifest("completed")
        if not completed:
            return None
        archive_path = self.path / "batch-results.zip"
        temporary_path = self.path / ".batch-results.zip.tmp"
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(self.path.iterdir()):
                if path.is_file() and not path.name.startswith(".") and path != archive_path:
                    archive.write(path, arcname=path.name)
        temporary_path.replace(archive_path)
        print(f"[subtitle-extractor][results] archive={archive_path}", flush=True)
        return archive_path

    def _write_manifest(self, status: str) -> None:
        completed = sum(item["status"] == "completed" for item in self.items)
        manifest = {
            "batchId": self.batch_id,
            "createdAt": self.created_at,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "total": self.total,
            "processed": len(self.items),
            "completed": completed,
            "failed": len(self.items) - completed,
            "outputDirectory": str(self.path),
            "items": self.items,
        }
        _atomic_write_text(self.path / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))


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


def _atomic_write_text(path: Path, content: str) -> None:
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)
