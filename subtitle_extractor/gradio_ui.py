from __future__ import annotations

from pathlib import Path
from typing import Any

from .asr import transcribe_audio
from .cookies import prepare_cookie_text
from .errors import AppError
from .formatting import compact_transcript
from .models import CookieInput, ExtractRequest, Segment
from .service import extract_subtitle_context
from .subtitles import format_ts


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
    from_upload = False
    if cookie_file_path:
        raw = Path(cookie_file_path).read_text(encoding="utf-8", errors="ignore").strip()
        from_upload = True
    return prepare_cookie_text(raw, from_upload=from_upload)


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


def build_uploaded_audio_context(
    audio_path: str,
    language: str,
    model: str,
    device: str,
    segments: list[Segment],
) -> tuple[str, str, str]:
    title = Path(audio_path).name
    plain_text = compact_transcript(segments)
    timeline = "\n".join(f"- [{format_ts(item.start)} - {format_ts(item.end)}] {item.text}" for item in segments)
    metadata = (
        "Platform: uploaded-audio\n"
        "Method: asr\n"
        f"Title: {title}\n"
        f"Track: faster-whisper/{model} / {language} / generated\n"
        f"Device: {device}\n"
        f"Segments: {len(segments)}"
    )
    ai_context = (
        "# Uploaded Audio Transcript Context\n\n"
        "## Metadata\n"
        "- Platform: Uploaded audio\n"
        f"- Source file: {title}\n"
        f"- Transcription: faster-whisper/{model}\n"
        f"- Language: {language}\n"
        f"- Device: {device}\n\n"
        "## Usage Notes\n"
        "The content below was transcribed from an uploaded local audio file and cleaned for use as AI Agent context.\n\n"
        "## Clean Transcript\n"
        f"{plain_text}\n\n"
        "## Timestamped Transcript\n"
        f"{timeline}\n"
    )
    return metadata, ai_context, plain_text


def transcribe_uploaded_audio(
    audio_file: str | None,
    language: str,
    asr_model: str,
    asr_device: str,
    hf_token: str,
    suppress_hf_warnings: bool,
    progress: Any = None,
) -> tuple[str, str, str, str]:
    if not audio_file:
        return "", "", "", "Upload an audio file first."

    def report(message: str, percent: int) -> None:
        if progress:
            progress(percent / 100, desc=message)

    try:
        report("Preparing uploaded audio", 10)
        segments = transcribe_audio(
            audio_file,
            language,
            asr_model,
            device_name=asr_device,
            hf_token=hf_token.strip() or None,
            suppress_hf_warnings=suppress_hf_warnings,
            progress=report,
        )
        report("Building AI Agent context", 95)
        metadata, ai_context, plain_text = build_uploaded_audio_context(
            audio_file,
            language,
            asr_model,
            asr_device,
            segments,
        )
        report("Done", 100)
        return metadata, ai_context, plain_text, ""
    except AppError as exc:
        return "", "", "", exc.message
    except Exception as exc:
        return "", "", "", str(exc)


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
        progress=gr.Progress(track_tqdm=False),
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

    def transcribe_audio_with_progress(
        audio_file: str | None,
        language: str,
        asr_model: str,
        asr_device: str,
        hf_token: str,
        suppress_hf_warnings: bool,
        progress=gr.Progress(track_tqdm=False),
    ) -> tuple[str, str, str, str]:
        return transcribe_uploaded_audio(
            audio_file,
            language,
            asr_model,
            asr_device,
            hf_token,
            suppress_hf_warnings,
            progress,
        )

    with gr.Blocks(title="Video Subtitle Extractor") as demo:
        gr.Markdown(
            "# Video Subtitle Extractor\n"
            "Cloud-ready Gradio UI for Bilibili/YouTube subtitle extraction and faster-whisper ASR."
        )
        gr.Markdown(runtime_summary())

        with gr.Tabs():
            with gr.Tab("Video URL"):
                with gr.Row():
                    platform = gr.Dropdown(PLATFORM_CHOICES, value="bilibili", label="Platform")
                    language = gr.Dropdown(LANGUAGE_CHOICES, value="auto", label="Subtitle / ASR Language")
                url = gr.Textbox(
                    label="Video URL",
                    placeholder="https://www.bilibili.com/video/BV... or https://www.youtube.com/watch?v=...",
                )

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
                ai_context = gr.Textbox(label="AI Agent Context", lines=18)
                plain_text = gr.Textbox(label="Clean Transcript", lines=12)

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
                    show_progress="full",
                )

            with gr.Tab("Uploaded Audio"):
                audio_file = gr.File(
                    label="Upload local audio",
                    file_types=[".mp3", ".m4a", ".webm", ".wav", ".flac", ".ogg", ".opus", ".mp4"],
                    type="filepath",
                )
                with gr.Row():
                    audio_language = gr.Dropdown(LANGUAGE_CHOICES, value="auto", label="ASR Language")
                    audio_model = gr.Dropdown(MODEL_CHOICES, value="base", label="faster-whisper model")
                    audio_device = gr.Dropdown(DEVICE_CHOICES, value="auto", label="ASR device")
                audio_hf_token = gr.Textbox(label="HF Token (optional)", type="password", placeholder="hf_...")
                audio_suppress_hf_warnings = gr.Checkbox(value=True, label="Hide HuggingFace symlink warning")
                transcribe = gr.Button("Transcribe Uploaded Audio", variant="primary")
                audio_error = gr.Textbox(label="Error", interactive=False)
                audio_metadata = gr.Textbox(label="Metadata", lines=8, interactive=False)
                audio_ai_context = gr.Textbox(label="AI Agent Context", lines=18)
                audio_plain_text = gr.Textbox(label="Clean Transcript", lines=12)

                transcribe.click(
                    transcribe_audio_with_progress,
                    inputs=[
                        audio_file,
                        audio_language,
                        audio_model,
                        audio_device,
                        audio_hf_token,
                        audio_suppress_hf_warnings,
                    ],
                    outputs=[audio_metadata, audio_ai_context, audio_plain_text, audio_error],
                    show_progress="full",
                )

    return demo
