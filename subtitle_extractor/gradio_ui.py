from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .cookies import normalize_cookie_header
from .errors import AppError
from .models import CookieInput, ExtractRequest
from .service import extract_subtitle_context


PLATFORM_CHOICES = ["bilibili", "youtube"]
LANGUAGE_CHOICES = ["auto", "zh-Hans", "zh-Hant", "zh", "en", "ja"]
MODEL_CHOICES = ["tiny", "base", "small", "medium", "large-v3"]
DEVICE_CHOICES = ["auto", "cuda", "cpu"]


def runtime_summary() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            return f"GPU available: {name}"
        return "GPU unavailable: using CPU fallback"
    except Exception:
        return "PyTorch unavailable: using CPU fallback unless CUDA is configured for faster-whisper"


def build_cookie_input(cookie_text: str | None, cookie_file_path: str | None) -> CookieInput:
    raw = (cookie_text or "").strip()
    if cookie_file_path:
        raw = Path(cookie_file_path).read_text(encoding="utf-8", errors="ignore").strip()
    if not raw:
        return CookieInput()
    if raw.lower().startswith("cookie:") or ("\t" not in raw and "=" in raw.splitlines()[0]):
        return CookieInput(header=normalize_cookie_header(raw))
    temp_file = tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False)
    temp_file.write(raw)
    temp_file.flush()
    temp_file.close()
    return CookieInput(temp_file=temp_file)


def format_metadata(data: dict[str, Any]) -> str:
    video = data.get("video") or {}
    track = data.get("selectedTrack") or {}
    return (
        f"Platform: {data.get('platform')}\n"
        f"Method: {data.get('extractionMethod')}\n"
        f"Title: {video.get('title')}\n"
        f"Creator: {video.get('uploader')}\n"
        f"URL: {video.get('url')}\n"
        f"Track: {track.get('source')} / {track.get('language')} / {track.get('ext')}\n"
        f"Segments: {len(data.get('segments') or [])}"
    )


def extract_with_progress(
    platform: str,
    url: str,
    language: str,
    enable_asr: bool,
    asr_model: str,
    asr_device: str,
    hf_token: str,
    suppress_hf_warnings: bool,
    cookie_text: str,
    cookie_file: str | None,
    progress: Any = None,
) -> tuple[str, str, str, str]:
    cookie_input = build_cookie_input(cookie_text, cookie_file)
    request = ExtractRequest(
        url=url,
        platform=platform,
        language=language,
        browser="none",
        enable_asr=enable_asr,
        asr_model=asr_model,
        asr_device=asr_device,
        hf_token=hf_token.strip() or None,
        suppress_hf_warnings=suppress_hf_warnings,
        cookie_text=cookie_text,
    )

    def report(message: str, percent: int) -> None:
        if progress:
            progress(percent / 100, desc=message)

    try:
        data = extract_subtitle_context(request, cookie_input, progress=report)
        metadata = format_metadata(data)
        return metadata, data["aiContext"], data["plainText"], ""
    except AppError as exc:
        return "", "", "", exc.message
    except Exception as exc:
        return "", "", "", str(exc)
    finally:
        cookie_input.cleanup()


def build_demo() -> Any:
    try:
        import gradio as gr
    except ImportError as exc:
        raise AppError("Gradio UI requires gradio. Install dependencies with: python -m pip install -r requirements.txt") from exc

    def run_with_progress(
        platform: str,
        url: str,
        language: str,
        enable_asr: bool,
        asr_model: str,
        asr_device: str,
        hf_token: str,
        suppress_hf_warnings: bool,
        cookie_text: str,
        cookie_file: str | None,
        progress: gr.Progress = gr.Progress(track_tqdm=False),
    ) -> tuple[str, str, str, str]:
        return extract_with_progress(
            platform,
            url,
            language,
            enable_asr,
            asr_model,
            asr_device,
            hf_token,
            suppress_hf_warnings,
            cookie_text,
            cookie_file,
            progress,
        )

    with gr.Blocks(title="Video Subtitle Extractor") as demo:
        gr.Markdown(
            "# Video Subtitle Extractor\n"
            "Cloud-ready Gradio UI for Bilibili/YouTube subtitle extraction and faster-whisper ASR."
        )
        gr.Markdown(runtime_summary())

        with gr.Row():
            platform = gr.Dropdown(PLATFORM_CHOICES, value="bilibili", label="Platform")
            language = gr.Dropdown(LANGUAGE_CHOICES, value="auto", label="Subtitle / ASR Language")
        url = gr.Textbox(label="Video URL", placeholder="https://www.bilibili.com/video/BV... or https://www.youtube.com/watch?v=...")

        with gr.Accordion("ASR fallback", open=True):
            enable_asr = gr.Checkbox(value=True, label="Use ASR when no subtitle track exists")
            with gr.Row():
                asr_model = gr.Dropdown(MODEL_CHOICES, value="base", label="faster-whisper model")
                asr_device = gr.Dropdown(DEVICE_CHOICES, value="auto", label="ASR device")
            hf_token = gr.Textbox(label="HF Token (optional)", type="password", placeholder="hf_...")
            suppress_hf_warnings = gr.Checkbox(value=True, label="Hide HuggingFace symlink warning")

        with gr.Accordion("Cookies", open=False):
            cookie_text = gr.Textbox(
                label="Paste raw Cookie header or Netscape cookies.txt",
                lines=6,
                placeholder="Cookie: SID=...; SAPISID=...\n\nor paste Netscape cookies.txt content",
            )
            cookie_file = gr.File(label="Upload cookies.txt", file_types=[".txt"], type="filepath")

        run = gr.Button("Extract", variant="primary")
        error = gr.Textbox(label="Error", interactive=False)
        metadata = gr.Textbox(label="Metadata", lines=8, interactive=False)
        ai_context = gr.Textbox(label="AI Agent Context", lines=18, show_copy_button=True)
        plain_text = gr.Textbox(label="Clean Transcript", lines=12, show_copy_button=True)

        run.click(
            run_with_progress,
            inputs=[
                platform,
                url,
                language,
                enable_asr,
                asr_model,
                asr_device,
                hf_token,
                suppress_hf_warnings,
                cookie_text,
                cookie_file,
            ],
            outputs=[metadata, ai_context, plain_text, error],
        )

    return demo
