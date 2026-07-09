from __future__ import annotations

import tempfile
from typing import Callable

import httpx
from yt_dlp.utils import DownloadError

from .asr import transcribe_audio
from .errors import AppError
from .formatting import build_ai_context, compact_transcript
from .models import CookieInput, ExtractRequest
from .subtitles import clean_text, format_ts, parse_subtitle
from .validation import browser_cookie_spec, ensure_supported_url, normalize_platform
from .ytdlp_client import choose_track, collect_tracks, download_audio, extract_video_info, fetch_subtitle


ProgressCallback = Callable[[str, int], None]


def emit(progress: ProgressCallback | None, message: str, percent: int) -> None:
    if progress:
        progress(message, percent)


def extract_subtitle_context(
    request: ExtractRequest,
    cookie_input: CookieInput,
    progress: ProgressCallback | None = None,
) -> dict:
    platform = normalize_platform(request.platform)
    video_url = ensure_supported_url(request.url, platform)
    browser_cookies = browser_cookie_spec(request.browser)

    try:
        emit(progress, "Reading video metadata", 10)
        info = extract_video_info(video_url, platform, cookie_input.path, browser_cookies, cookie_input.header)
        emit(progress, "Checking subtitle tracks", 25)
        tracks = collect_tracks(info)
        extraction_method = "subtitle"
        try:
            track = choose_track(tracks, request.language)
            emit(progress, f"Downloading subtitle track {track['language']}/{track['ext']}", 45)
            raw_subtitle = fetch_subtitle(track, cookie_input.path, cookie_input.header, platform)
            emit(progress, "Parsing subtitle content", 65)
            segments = parse_subtitle(raw_subtitle, track.get("ext") or "")
        except AppError as exc:
            if exc.status_code != 404 or not request.enable_asr:
                raise
            emit(progress, "No subtitle track found. Preparing ASR fallback", 35)
            with tempfile.TemporaryDirectory(prefix="subtitle-asr-") as temp_dir:
                emit(progress, "Downloading audio for ASR", 45)
                audio_path = download_audio(video_url, platform, cookie_input.path, browser_cookies, cookie_input.header, temp_dir)
                segments = transcribe_audio(
                    audio_path,
                    request.language,
                    request.asr_model,
                    device_name=request.asr_device,
                    hf_token=request.hf_token,
                    suppress_hf_warnings=request.suppress_hf_warnings,
                    progress=progress,
                )
            extraction_method = "asr"
            track = {
                "language": request.language if request.language != "auto" else "auto",
                "source": "asr:faster-whisper",
                "ext": "generated",
                "name": f"faster-whisper/{request.asr_model}",
            }
        emit(progress, "Building AI Agent context", 95)
        ai_context = build_ai_context(info, track, segments, platform)

        result = {
            "platform": platform,
            "extractionMethod": extraction_method,
            "video": {
                "title": clean_text(info.get("title") or ""),
                "uploader": clean_text(info.get("uploader") or info.get("channel") or ""),
                "url": info.get("webpage_url") or video_url,
                "duration": info.get("duration"),
            },
            "selectedTrack": {key: track[key] for key in ("language", "source", "ext", "name")},
            "availableTracks": [
                {key: item[key] for key in ("language", "source", "ext", "name")}
                for item in tracks
            ],
            "segments": [
                {
                    "start": item.start,
                    "end": item.end,
                    "startText": format_ts(item.start),
                    "endText": format_ts(item.end),
                    "text": item.text,
                }
                for item in segments
            ],
            "plainText": compact_transcript(segments),
            "aiContext": ai_context,
        }
        emit(progress, "Done", 100)
        return result
    except DownloadError as exc:
        raise map_download_error(exc, platform) from exc
    except httpx.HTTPError as exc:
        raise AppError(f"Failed to download subtitle content: {exc}", status_code=502) from exc


def map_download_error(exc: DownloadError, platform: str):
    from .errors import AppError

    message = str(exc)
    if platform == "bilibili" and ("HTTP Error 412" in message or "Precondition Failed" in message):
        return AppError(
            "Bilibili returned HTTP 412. Provide a logged-in cookies.txt file or browser cookies and retry.",
            status_code=502,
        )
    if platform == "youtube" and ("Sign in to confirm" in message or "not a bot" in message):
        return AppError(
            "YouTube requires sign-in to confirm this request is not a bot. "
            "Log in to YouTube in your browser, then provide browser cookies or upload a YouTube cookies.txt file.",
            status_code=502,
        )
    if platform == "youtube" and "Requested format is not available" in message:
        return AppError(
            "YouTube did not expose a downloadable audio/video format for this request. "
            "The app can still extract existing subtitle tracks when YouTube exposes them, but ASR needs audio download. "
            "On Colab/cloud IPs this can still be caused by YouTube anti-bot checks even with cookies.",
            status_code=502,
        )
    if "Could not copy Chrome cookie database" in message:
        return AppError(
            "Unable to read browser cookies. Close the browser and retry, or paste the Cookie request header manually.",
            status_code=502,
        )
    return AppError(f"yt-dlp failed to parse the video: {message}", status_code=502)
