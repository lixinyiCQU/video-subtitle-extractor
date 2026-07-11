from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from .config import ASR_SUPPORTED_DEVICES, ASR_SUPPORTED_MODELS, DEFAULT_ASR_DEVICE, DEFAULT_ASR_MODEL
from .errors import AppError
from .models import Segment


def normalize_asr_model(model_name: str | None) -> str:
    value = (model_name or DEFAULT_ASR_MODEL).strip()
    if value not in ASR_SUPPORTED_MODELS:
        raise AppError(f"Unsupported ASR model '{value}'. Supported models: {', '.join(ASR_SUPPORTED_MODELS)}")
    return value


def normalize_asr_device(device_name: str | None) -> str:
    value = (device_name or DEFAULT_ASR_DEVICE).strip().lower()
    if value not in ASR_SUPPORTED_DEVICES:
        raise AppError(f"Unsupported ASR device '{value}'. Supported devices: {', '.join(ASR_SUPPORTED_DEVICES)}")
    return value


def cuda_is_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def resolve_asr_runtime(device_name: str | None) -> tuple[str, str]:
    requested = normalize_asr_device(device_name)
    if requested == "cuda":
        if not cuda_is_available():
            raise AppError("CUDA was requested, but no CUDA GPU is available in this runtime.", status_code=422)
        return "cuda", "float16"
    if requested == "auto" and cuda_is_available():
        return "cuda", "float16"
    return "cpu", "int8"


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


def log_asr(message: str) -> None:
    print(f"[subtitle-extractor][asr] {message}", flush=True)


def estimate_transcription_percent(segment_end: float, duration: float) -> int:
    if duration <= 0:
        return 75
    return min(89, 75 + int((max(segment_end, 0) / duration) * 14))


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
    device_name: str | None = None,
    hf_token: str | None = None,
    suppress_hf_warnings: bool = True,
    progress: ProgressCallback | None = None,
) -> list[Segment]:
    model_key = normalize_asr_model(model_name)
    device, compute_type = resolve_asr_runtime(device_name)
    audio_path = Path(audio_path)
    log_asr(f"start audio={audio_path.name} model={model_key} device={device} compute_type={compute_type}")
    with huggingface_environment(hf_token, suppress_hf_warnings):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise AppError(
                "ASR fallback requires faster-whisper. Install dependencies with: python -m pip install -r requirements.txt",
                status_code=500,
            ) from exc

        if progress:
            progress(f"Loading faster-whisper model '{model_key}' on {device}", 65)
        log_asr(f"loading model {model_key} on {device}")
        model = WhisperModel(model_key, device=device, compute_type=compute_type)
        log_asr("model loaded")
        if progress:
            progress("Transcribing audio with faster-whisper", 75)
        log_asr("transcription started")
        segments, info = model.transcribe(
            str(audio_path),
            language=language_for_asr(language),
            vad_filter=True,
            beam_size=5,
        )

    result: list[Segment] = []
    duration = float(getattr(info, "duration", 0) or 0)
    log_asr(f"audio duration={duration:.2f}s")
    last_reported_percent = 75
    last_log_time = time.monotonic()
    for item in segments:
        text = item.text.strip()
        if text:
            result.append(Segment(start=float(item.start), end=float(item.end), text=text))
        if progress and duration > 0:
            percent = estimate_transcription_percent(float(item.end), duration)
            if percent > last_reported_percent:
                last_reported_percent = percent
                progress(f"Transcribing audio with faster-whisper ({percent}%)", percent)
        now = time.monotonic()
        if now - last_log_time >= 30:
            log_asr(f"transcribing segment_count={len(result)} last_end={float(item.end):.2f}s")
            last_log_time = now
    if progress:
        progress("Finalizing ASR transcript", 90)
    log_asr(f"transcription finished segments={len(result)}")
    if not result:
        raise AppError("ASR completed, but no speech segments were detected.", status_code=422)
    return result
