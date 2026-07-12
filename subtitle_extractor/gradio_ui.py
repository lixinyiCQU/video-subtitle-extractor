from __future__ import annotations

import queue
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable, Iterator

from .asr import transcribe_audio
from .batch import extract_batch_context, parse_video_urls
from .cookies import prepare_cookie_text
from .errors import AppError
from .exports import create_result_exports
from .formatting import compact_transcript
from .models import CookieInput, ExtractRequest, Segment
from .subtitles import format_ts
from .validation import detect_platform


LANGUAGE_CHOICES = ["auto", "zh-Hans", "zh-Hant", "zh", "en", "ja"]
MODEL_CHOICES = ["tiny", "base", "small", "medium", "large-v3"]
DEVICE_CHOICES = ["auto", "cuda", "cpu"]
StreamOutput = tuple[str, str, str, str, str]
WorkResult = tuple[str, str, str, str]
ProgressCallback = Callable[[str, int], None]


def log_event(task_id: str, message: str) -> None:
    print(f"[subtitle-extractor][{task_id}] {message}", flush=True)


class ProgressAdapter:
    def __init__(self, callback: ProgressCallback, task_id: str) -> None:
        self.callback = callback
        self.task_id = task_id

    def __call__(self, value: float, desc: str | None = None) -> None:
        message = desc or "Working"
        percent = int(float(value or 0) * 100)
        log_event(self.task_id, f"progress {percent}% - {message}")
        self.callback(message, percent)


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


def completed_batch_results(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        item["result"]
        for item in (items or [])
        if item.get("status") == "completed" and item.get("result")
    ]


def batch_result_choices(items: list[dict[str, Any]] | None) -> list[tuple[str, str]]:
    return [
        ((result.get("video") or {}).get("title") or f"Video {index + 1}", str(index))
        for index, result in enumerate(completed_batch_results(items))
    ]


def view_batch_result(selection: str | int | None, items: list[dict[str, Any]] | None) -> tuple[str, str, str]:
    results = completed_batch_results(items)
    if not results:
        return "", "", ""
    try:
        index = int(selection or 0)
    except (TypeError, ValueError):
        index = 0
    index = max(0, min(index, len(results) - 1))
    result = results[index]
    return format_metadata(result), result["aiContext"], result["plainText"]


def export_gradio_batch(items: list[dict[str, Any]] | None) -> tuple[list[str], str]:
    results = completed_batch_results(items)
    if not results:
        return [], "No completed video result is available for export."
    artifacts = create_result_exports(results)
    return [str(artifact.path) for artifact in artifacts], ""


def extract_batch_with_progress(
    urls_text: str,
    language: str,
    enable_asr: bool,
    asr_model: str,
    asr_device: str,
    hf_token: str,
    suppress_hf_warnings: bool,
    bilibili_cookie_text: str,
    bilibili_cookie_file: str | None,
    youtube_cookie_text: str,
    youtube_cookie_file: str | None,
    progress: ProgressCallback | None = None,
) -> tuple[list[dict[str, Any]], str]:
    urls = parse_video_urls(urls_text)
    cookie_inputs = {
        "bilibili": build_cookie_input(bilibili_cookie_text, bilibili_cookie_file),
        "youtube": build_cookie_input(youtube_cookie_text, youtube_cookie_file),
    }
    cookie_texts = {"bilibili": bilibili_cookie_text, "youtube": youtube_cookie_text}
    try:
        detected_urls = [(url, detect_platform(url)) for url in urls]
        requests = [
            ExtractRequest(
                url=url,
                platform=platform,
                language=language,
                browser="none",
                enable_asr=enable_asr,
                asr_model=asr_model,
                asr_device=asr_device,
                hf_token=hf_token.strip() or None,
                suppress_hf_warnings=suppress_hf_warnings,
                cookie_text=cookie_texts[platform],
            )
            for url, platform in detected_urls
        ]
        batch = extract_batch_context(requests, cookie_inputs, progress=progress)
        items = batch["items"]
        failures = [f"{item['url']}: {item['error']}" for item in items if item["status"] == "failed"]
        messages = [f"Results saved to: {batch['outputDirectory']}", *failures]
        return items, "\n".join(messages)
    finally:
        for cookie_input in cookie_inputs.values():
            cookie_input.cleanup()


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


def resolve_audio_source(audio_file: str | None, server_audio_path: str | None) -> str:
    if audio_file:
        return audio_file
    value = (server_audio_path or "").strip()
    if not value:
        raise AppError("Upload an audio file or provide an audio file path on the server.", status_code=422)
    path = Path(value).expanduser()
    if not path.exists() or not path.is_file():
        raise AppError(f"Server audio file was not found: {path}", status_code=422)
    return str(path)


def stream_status(worker: Callable[[ProgressCallback, str], WorkResult], start_message: str) -> Iterator[StreamOutput]:
    task_id = uuid.uuid4().hex[:8]
    events: queue.Queue[tuple[str, int] | WorkResult] = queue.Queue()
    status_lines = [f"Task {task_id}", f"0% - {start_message}"]
    latest_status = "\n".join(status_lines)
    latest_payload: StreamOutput = (latest_status, "", "", "", "")
    started_at = time.monotonic()
    last_console_heartbeat = started_at

    log_event(task_id, start_message)

    def progress(message: str, percent: int) -> None:
        events.put((message, percent))

    def run_worker() -> None:
        try:
            log_event(task_id, "worker started")
            result = worker(progress, task_id)
            log_event(task_id, "worker completed")
            events.put(result)
        except AppError as exc:
            log_event(task_id, f"application error: {exc.message}")
            events.put(("", "", "", exc.message))
        except Exception as exc:
            log_event(task_id, f"unexpected error: {exc}")
            print(traceback.format_exc(), flush=True)
            events.put(("", "", "", str(exc)))

    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()
    yield latest_payload

    while thread.is_alive() or not events.empty():
        try:
            event = events.get(timeout=1)
        except queue.Empty:
            now = time.monotonic()
            elapsed = int(now - started_at)
            heartbeat = f"{status_lines[-1]}\nRunning for {elapsed}s"
            latest_payload = (heartbeat, *latest_payload[1:])
            if now - last_console_heartbeat >= 30:
                log_event(task_id, f"heartbeat running for {elapsed}s; last status: {status_lines[-1]}")
                last_console_heartbeat = now
            yield latest_payload
            continue

        if len(event) == 2 and isinstance(event[1], int):
            message, percent = event
            percent = max(0, min(100, int(percent)))
            line = f"{percent}% - {message}"
            if not status_lines or status_lines[-1] != line:
                status_lines.append(line)
            latest_status = "\n".join(status_lines[-12:])
            latest_payload = (latest_status, *latest_payload[1:])
            yield latest_payload
        else:
            metadata, ai_context, plain_text, error = event
            if error:
                status_lines.append(f"Failed - {error}")
                log_event(task_id, f"failed: {error}")
            else:
                status_lines.append("100% - Done")
                log_event(task_id, "done")
            latest_status = "\n".join(status_lines[-12:])
            latest_payload = (latest_status, metadata, ai_context, plain_text, error)
            yield latest_payload


def transcribe_uploaded_audio(
    audio_file: str | None,
    server_audio_path: str | None,
    language: str,
    asr_model: str,
    asr_device: str,
    hf_token: str,
    suppress_hf_warnings: bool,
    progress: Any = None,
) -> tuple[str, str, str, str]:
    def report(message: str, percent: int) -> None:
        if progress:
            progress(percent / 100, desc=message)

    try:
        audio_path = resolve_audio_source(audio_file, server_audio_path)
        report("Preparing uploaded audio", 10)
        segments = transcribe_audio(
            audio_path,
            language,
            asr_model,
            device_name=asr_device,
            hf_token=hf_token.strip() or None,
            suppress_hf_warnings=suppress_hf_warnings,
            progress=report,
        )
        report("Building AI Agent context", 95)
        metadata, ai_context, plain_text = build_uploaded_audio_context(
            audio_path,
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


def build_demo() -> Any:
    try:
        import gradio as gr
    except ImportError as exc:
        raise AppError("Gradio UI requires gradio. Install dependencies with: python -m pip install -r requirements.txt") from exc

    def run_with_progress(
        urls_text: str,
        language: str,
        enable_asr: bool,
        asr_model: str,
        asr_device: str,
        hf_token: str,
        suppress_hf_warnings: bool,
        bilibili_cookie_text: str,
        bilibili_cookie_file: str | None,
        youtube_cookie_text: str,
        youtube_cookie_file: str | None,
    ) -> Iterator[tuple[Any, ...]]:
        task_id = uuid.uuid4().hex[:8]
        events: queue.Queue[tuple[Any, ...]] = queue.Queue()
        status_lines = [f"Task {task_id}", "0% - Queued batch extraction"]
        empty_selector = gr.Dropdown(label="View Video Subtitle", choices=[], value=None, interactive=False)

        def progress(message: str, percent: int) -> None:
            events.put(("progress", message, percent))

        def worker() -> None:
            try:
                items, batch_error = extract_batch_with_progress(
                    urls_text,
                    language,
                    enable_asr,
                    asr_model,
                    asr_device,
                    hf_token,
                    suppress_hf_warnings,
                    bilibili_cookie_text,
                    bilibili_cookie_file,
                    youtube_cookie_text,
                    youtube_cookie_file,
                    progress,
                )
                events.put(("done", items, batch_error))
            except AppError as exc:
                events.put(("failed", exc.message))
            except Exception as exc:
                print(traceback.format_exc(), flush=True)
                events.put(("failed", str(exc)))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        yield "\n".join(status_lines), empty_selector, [], "", "", "", ""
        while thread.is_alive() or not events.empty():
            try:
                event = events.get(timeout=1)
            except queue.Empty:
                yield "\n".join(status_lines[-12:]), empty_selector, [], "", "", "", ""
                continue
            if event[0] == "progress":
                _, message, percent = event
                status_lines.append(f"{percent}% - {message}")
                yield "\n".join(status_lines[-12:]), empty_selector, [], "", "", "", ""
                continue
            if event[0] == "failed":
                error_message = event[1]
                status_lines.append(f"Failed - {error_message}")
                yield "\n".join(status_lines[-12:]), empty_selector, [], "", "", "", error_message
                continue

            _, items, batch_error = event
            choices = batch_result_choices(items)
            selected = choices[0][1] if choices else None
            selector_update = gr.Dropdown(
                label="View Video Subtitle",
                choices=choices,
                value=selected,
                interactive=bool(choices),
            )
            metadata_value, context_value, plain_value = view_batch_result(selected, items)
            completed = len(completed_batch_results(items))
            status_lines.append(f"100% - Completed {completed}/{len(items)} videos")
            yield (
                "\n".join(status_lines[-12:]),
                selector_update,
                items,
                metadata_value,
                context_value,
                plain_value,
                batch_error,
            )

    def transcribe_audio_with_progress(
        audio_file: str | None,
        server_audio_path: str | None,
        language: str,
        asr_model: str,
        asr_device: str,
        hf_token: str,
        suppress_hf_warnings: bool,
    ) -> Iterator[StreamOutput]:
        def worker(progress: ProgressCallback, task_id: str) -> WorkResult:
            return transcribe_uploaded_audio(
                audio_file,
                server_audio_path,
                language,
                asr_model,
                asr_device,
                hf_token,
                suppress_hf_warnings,
                ProgressAdapter(progress, task_id),
            )

        yield from stream_status(worker, "Queued audio transcription")

    with gr.Blocks(title="Video Subtitle Extractor") as demo:
        gr.Markdown(
            "# Video Subtitle Extractor\n"
            "Cloud-ready Gradio UI for Bilibili/YouTube subtitle extraction and faster-whisper ASR."
        )
        gr.Markdown(runtime_summary())

        with gr.Tabs():
            with gr.Tab("Video URL"):
                language = gr.Dropdown(LANGUAGE_CHOICES, value="auto", label="Subtitle / ASR Language")
                url = gr.Textbox(
                    label="Video URLs (one per line, up to 50)",
                    lines=5,
                    placeholder="https://www.bilibili.com/video/BV...\nhttps://www.youtube.com/watch?v=...",
                )

                with gr.Accordion("ASR fallback", open=True):
                    enable_asr = gr.Checkbox(value=True, label="Use ASR when no subtitle track exists")
                    with gr.Row():
                        asr_model = gr.Dropdown(MODEL_CHOICES, value="base", label="faster-whisper model")
                        asr_device = gr.Dropdown(DEVICE_CHOICES, value="auto", label="ASR device")
                    hf_token = gr.Textbox(label="HF Token (optional)", type="password", placeholder="hf_...")
                    suppress_hf_warnings = gr.Checkbox(value=True, label="Hide HuggingFace symlink warning")

                with gr.Accordion("Cookies", open=False):
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### Bilibili Cookies")
                            bilibili_cookie_text = gr.Textbox(
                                label="Paste Bilibili Cookie header or cookies.txt",
                                lines=6,
                                placeholder="Cookie: SESSDATA=...; bili_jct=...",
                            )
                            bilibili_cookie_file = gr.File(
                                label="Upload Bilibili cookies.txt",
                                file_types=[".txt"],
                                type="filepath",
                            )
                        with gr.Column():
                            gr.Markdown("### YouTube Cookies")
                            youtube_cookie_text = gr.Textbox(
                                label="Paste YouTube Cookie header or cookies.txt",
                                lines=6,
                                placeholder="Cookie: SID=...; SAPISID=...",
                            )
                            youtube_cookie_file = gr.File(
                                label="Upload YouTube cookies.txt",
                                file_types=[".txt"],
                                type="filepath",
                            )

                run = gr.Button("Extract Batch", variant="primary")
                error = gr.Textbox(label="Batch Messages / Errors", interactive=False)
                progress_status = gr.Textbox(label="Progress", lines=8, interactive=False)
                result_selector = gr.Dropdown(label="View Video Subtitle", choices=[], interactive=False)
                batch_state = gr.State([])
                metadata = gr.Textbox(label="Metadata", lines=8, interactive=False)
                ai_context = gr.Textbox(label="AI Agent Context", lines=18)
                plain_text = gr.Textbox(label="Clean Transcript", lines=12)
                export = gr.Button("Export Metadata and Subtitles")
                export_files = gr.File(label="Export Files", file_count="multiple", interactive=False)
                export_error = gr.Textbox(label="Export Error", interactive=False)

                run.click(
                    run_with_progress,
                    inputs=[
                        url,
                        language,
                        enable_asr,
                        asr_model,
                        asr_device,
                        hf_token,
                        suppress_hf_warnings,
                        bilibili_cookie_text,
                        bilibili_cookie_file,
                        youtube_cookie_text,
                        youtube_cookie_file,
                    ],
                    outputs=[progress_status, result_selector, batch_state, metadata, ai_context, plain_text, error],
                    show_progress="full",
                )
                result_selector.input(
                    view_batch_result,
                    inputs=[result_selector, batch_state],
                    outputs=[metadata, ai_context, plain_text],
                    show_progress="hidden",
                )
                export.click(
                    export_gradio_batch,
                    inputs=[batch_state],
                    outputs=[export_files, export_error],
                    show_progress="full",
                )

            with gr.Tab("Uploaded Audio"):
                audio_file = gr.File(
                    label="Upload local audio",
                    file_types=[".mp3", ".m4a", ".webm", ".wav", ".flac", ".ogg", ".opus", ".mp4"],
                    type="filepath",
                )
                server_audio_path = gr.Textbox(
                    label="Audio file path on server",
                    placeholder="/workspace/audio/example.mp3",
                )
                with gr.Row():
                    audio_language = gr.Dropdown(LANGUAGE_CHOICES, value="auto", label="ASR Language")
                    audio_model = gr.Dropdown(MODEL_CHOICES, value="base", label="faster-whisper model")
                    audio_device = gr.Dropdown(DEVICE_CHOICES, value="auto", label="ASR device")
                audio_hf_token = gr.Textbox(label="HF Token (optional)", type="password", placeholder="hf_...")
                audio_suppress_hf_warnings = gr.Checkbox(value=True, label="Hide HuggingFace symlink warning")
                transcribe = gr.Button("Transcribe Uploaded Audio", variant="primary")
                audio_error = gr.Textbox(label="Error", interactive=False)
                audio_progress_status = gr.Textbox(label="Progress", lines=8, interactive=False)
                audio_metadata = gr.Textbox(label="Metadata", lines=8, interactive=False)
                audio_ai_context = gr.Textbox(label="AI Agent Context", lines=18)
                audio_plain_text = gr.Textbox(label="Clean Transcript", lines=12)

                transcribe.click(
                    transcribe_audio_with_progress,
                    inputs=[
                        audio_file,
                        server_audio_path,
                        audio_language,
                        audio_model,
                        audio_device,
                        audio_hf_token,
                        audio_suppress_hf_warnings,
                    ],
                    outputs=[audio_progress_status, audio_metadata, audio_ai_context, audio_plain_text, audio_error],
                    show_progress="full",
                )

    return demo
