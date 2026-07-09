from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class CookieInput:
    temp_file: tempfile.NamedTemporaryFile | None = None
    header: str | None = None

    @property
    def path(self) -> str | None:
        return self.temp_file.name if self.temp_file else None

    def cleanup(self) -> None:
        if not self.temp_file:
            return
        try:
            Path(self.temp_file.name).unlink(missing_ok=True)
        except OSError:
            pass


@dataclass(frozen=True)
class ExtractRequest:
    url: str
    platform: str
    language: str
    browser: str
    enable_asr: bool = True
    asr_model: str = "base"
    hf_token: str | None = None
    suppress_hf_warnings: bool = True
    cookie_text: str | None = None


Track = dict[str, Any]
VideoInfo = dict[str, Any]
