from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from .config import ASR_SUPPORTED_MODELS, DEFAULT_ASR_MODEL
from .errors import AppError
from .models import Segment


def normalize_asr_model(model_name: str | None) -> str:
    value = (model_name or DEFAULT_ASR_MODEL).strip()
    if value not in ASR_SUPPORTED_MODELS:
        raise AppError(f"Unsupported ASR model '{value}'. Supported models: {', '.join(ASR_SUPPORTED_MODELS)}")
    return value


def language_for_asr(language: str | None) -> str | None:
    value = (language or "auto").strip().lower()
    if value == "auto":
        return None
    if value.startswith("zh"):
        return "zh"
    if value.startswith("en"):
        return "en"
    if value.startswith("ja"):
        return "ja"
    return value.split("-", 1)[0]


ProgressCallback = Callable[[str, int], None]


@contextmanager
def huggingface_environment(hf_token: str | None, suppress_warnings: bool) -> Iterator[None]:
    old_token = os.environ.get("HF_TOKEN")
    old_symlink_warning = os.environ.get("HF_HUB_DISABLE_SYMLINKS_WARNING")
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token.strip()
    if suppress_warnings:
        os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    try:
        yield
    finally:
        if old_token is None:
            os.environ.pop("HF_TOKEN", None)
        else:
            os.environ["HF_TOKEN"] = old_token
        if old_symlink_warning is None:
            os.environ.pop("HF_HUB_DISABLE_SYMLINKS_WARNING", None)
        else:
            os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = old_symlink_warning


def transcribe_audio(
    audio_path: str | Path,
    language: str | None,
    model_name: str | None,
    hf_token: str | None = None,
    suppress_hf_warnings: bool = True,
    progress: ProgressCallback | None = None,
) -> list[Segment]:
    model_key = normalize_asr_model(model_name)
    with huggingface_environment(hf_token, suppress_hf_warnings):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise AppError(
                "ASR fallback requires faster-whisper. Install dependencies with: python -m pip install -r requirements.txt",
                status_code=500,
            ) from exc

        if progress:
            progress(f"Loading faster-whisper model '{model_key}'", 65)
        model = WhisperModel(model_key, device="cpu", compute_type="int8")
        if progress:
            progress("Transcribing audio with faster-whisper", 75)
        segments, _info = model.transcribe(
            str(audio_path),
            language=language_for_asr(language),
            vad_filter=True,
            beam_size=5,
        )

    result: list[Segment] = []
    for item in segments:
        text = item.text.strip()
        if text:
            result.append(Segment(start=float(item.start), end=float(item.end), text=text))
    if progress:
        progress("Finalizing ASR transcript", 90)
    if not result:
        raise AppError("ASR completed, but no speech segments were detected.", status_code=422)
    return result
