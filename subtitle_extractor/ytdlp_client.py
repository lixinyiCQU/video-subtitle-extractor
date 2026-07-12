from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import httpx
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .config import ASR_AUDIO_FORMATS, PREFERRED_LANGUAGES, PREFERRED_SUBTITLE_EXTENSIONS, SUBTITLE_FORMATS
from .cookies import load_cookie_jar
from .errors import AppError
from .http_headers import request_headers
from .models import Track, VideoInfo
from .subtitles import normalize_language_key


class QuietYtdlpLogger:
    def debug(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        print(f"[subtitle-extractor][yt-dlp] {_strip_ansi(message)}", flush=True)


class DownloadProgressLogger:
    def __init__(self) -> None:
        self.last_log_time = 0.0

    def __call__(self, status: dict[str, Any]) -> None:
        state = status.get("status")
        now = time.monotonic()
        if state == "downloading" and now - self.last_log_time >= 15:
            downloaded = int(status.get("downloaded_bytes") or 0)
            total = int(status.get("total_bytes") or status.get("total_bytes_estimate") or 0)
            speed = int(status.get("speed") or 0)
            eta = status.get("eta")
            print(
                f"[subtitle-extractor][download] downloaded={_format_bytes(downloaded)} "
                f"total={_format_bytes(total) if total else 'unknown'} speed={_format_bytes(speed)}/s eta={eta}",
                flush=True,
            )
            self.last_log_time = now
        elif state == "finished":
            downloaded = int(status.get("downloaded_bytes") or 0)
            print(
                f"[subtitle-extractor][download] finished bytes={_format_bytes(downloaded)}",
                flush=True,
            )


def ydl_options(
    cookie_path: str | None = None,
    browser_cookies: tuple[str, str | None, str | None, str | None] | None = None,
    cookie_header: str | None = None,
    platform: str = "bilibili",
) -> dict[str, Any]:
    headers = request_headers(platform)
    if cookie_header:
        headers["Cookie"] = cookie_header
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["all"],
        "subtitlesformat": SUBTITLE_FORMATS,
        "http_headers": headers,
        "logger": QuietYtdlpLogger(),
        "ignore_no_formats_error": True,
        "noplaylist": True,
        "socket_timeout": 45,
        "retries": 8,
        "extractor_retries": 5,
    }
    if cookie_path:
        opts["cookiefile"] = cookie_path
    if browser_cookies:
        opts["cookiesfrombrowser"] = browser_cookies
    if platform == "youtube":
        opts["js_runtimes"] = {"node": {}}
        opts["remote_components"] = {"ejs:github"}
    return opts


def extract_video_info(
    url: str,
    platform: str,
    cookie_path: str | None,
    browser_cookies: tuple[str, str | None, str | None, str | None] | None,
    cookie_header: str | None,
) -> VideoInfo:
    last_error: DownloadError | None = None
    for attempt in range(1, 4):
        print(
            f"[subtitle-extractor][metadata] extracting platform={platform} attempt={attempt}/3",
            flush=True,
        )
        try:
            with YoutubeDL(ydl_options(cookie_path, browser_cookies, cookie_header, platform)) as ydl:
                info = ydl.extract_info(url, download=False)
            break
        except DownloadError as exc:
            last_error = exc
            if attempt < 3 and _is_transient_download_error(_strip_ansi(str(exc))):
                print(
                    "[subtitle-extractor][metadata] transient network error; retrying metadata extraction",
                    flush=True,
                )
                time.sleep(attempt * 2)
                continue
            raise
    else:
        raise AppError("Unable to parse video metadata after retries.", status_code=502) from last_error
    if not isinstance(info, dict):
        raise AppError("Unable to parse video metadata.", status_code=422)
    return info


def download_audio(
    url: str,
    platform: str,
    cookie_path: str | None,
    browser_cookies: tuple[str, str | None, str | None, str | None] | None,
    cookie_header: str | None,
    output_dir: str | Path,
) -> Path:
    headers = request_headers(platform)
    if cookie_header:
        headers["Cookie"] = cookie_header

    base_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "outtmpl": str(Path(output_dir) / "%(id)s.%(ext)s"),
        "http_headers": headers,
        "noplaylist": True,
        "logger": QuietYtdlpLogger(),
        "socket_timeout": 45,
        "retries": 8,
        "fragment_retries": 8,
        "extractor_retries": 5,
        "file_access_retries": 5,
        "http_chunk_size": 512 * 1024,
        "concurrent_fragment_downloads": 1,
        "continuedl": True,
        "retry_sleep_functions": {
            "http": lambda n: min(2 ** max(n - 1, 0), 20),
            "fragment": lambda n: min(2 ** max(n - 1, 0), 20),
            "extractor": lambda n: min(n * 2, 10),
        },
    }
    if cookie_path:
        base_opts["cookiefile"] = cookie_path
    if browser_cookies:
        base_opts["cookiesfrombrowser"] = browser_cookies
    if platform == "youtube":
        base_opts["js_runtimes"] = {"node": {}}
        base_opts["remote_components"] = {"ejs:github"}

    last_error: DownloadError | None = None
    filename: str | None = None
    for format_selector in ASR_AUDIO_FORMATS:
        format_unavailable = False
        for attempt in range(1, 3):
            opts = {
                **base_opts,
                "format": format_selector,
                "progress_hooks": [DownloadProgressLogger()],
            }
            print(
                f"[subtitle-extractor][download] start platform={platform} "
                f"format={format_selector} attempt={attempt}/2",
                flush=True,
            )
            try:
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                break
            except DownloadError as exc:
                last_error = exc
                message = _strip_ansi(str(exc))
                if "Requested format is not available" in message:
                    format_unavailable = True
                    break
                if attempt < 2 and _is_transient_download_error(message):
                    print(
                        "[subtitle-extractor][download] transient network error; refreshing media URL before retry",
                        flush=True,
                    )
                    time.sleep(2 * attempt)
                    continue
                raise
        if not format_unavailable and filename:
            break
    else:
        raise AppError(
            "No downloadable audio format is available for this video. "
            "For YouTube, log in and provide browser cookies or upload a YouTube cookies.txt file.",
            status_code=502,
        ) from last_error

    path = Path(filename)
    if not path.exists():
        candidates = sorted(Path(output_dir).glob("*"), key=lambda item: item.stat().st_mtime, reverse=True)
        if candidates:
            path = candidates[0]
    if not path.exists():
        raise AppError("Audio download completed, but the output audio file was not found.", status_code=502)
    return path


def _is_transient_download_error(message: str) -> bool:
    value = message.casefold()
    return any(
        marker in value
        for marker in (
            "timed out",
            "timeout",
            "connection reset",
            "remote end closed",
            "temporarily unavailable",
            "http error 500",
            "http error 502",
            "http error 503",
            "http error 504",
        )
    )


def _strip_ansi(value: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", value)


def _format_bytes(value: int) -> str:
    amount = float(max(value, 0))
    for unit in ("B", "KiB", "MiB", "GiB"):
        if amount < 1024 or unit == "GiB":
            return f"{amount:.1f}{unit}"
        amount /= 1024
    return f"{amount:.1f}GiB"


def collect_tracks(info: VideoInfo) -> list[Track]:
    tracks: list[Track] = []
    for source_key, source_label in (("subtitles", "official"), ("automatic_captions", "automatic")):
        for lang, entries in (info.get(source_key) or {}).items():
            if not entries:
                continue
            for entry in entries:
                ext = (entry.get("ext") or "unknown").lower()
                if normalize_language_key(lang) in {"danmaku", "live-chat"} or ext in {"xml", "json3"}:
                    continue
                if not entry.get("url") and not entry.get("data"):
                    continue
                tracks.append(
                    {
                        "language": lang,
                        "source": source_label,
                        "ext": entry.get("ext") or "unknown",
                        "url": entry.get("url"),
                        "name": entry.get("name") or entry.get("format_id") or lang,
                        "data": entry,
                    }
                )
    return tracks


def choose_track(tracks: list[Track], language: str | None) -> Track:
    if not tracks:
        raise AppError(
            "No extractable subtitles were found. Try providing cookies or confirm the video has captions enabled.",
            status_code=404,
        )

    if language and language != "auto":
        requested = normalize_language_key(language)
        exact = [track for track in tracks if normalize_language_key(track["language"]) == requested]
        if exact:
            return prefer_ext(exact)
        prefix = [track for track in tracks if normalize_language_key(track["language"]).startswith(requested)]
        if prefix:
            return prefer_ext(prefix)

    normalized = [(normalize_language_key(track["language"]), track) for track in tracks]
    for lang in PREFERRED_LANGUAGES:
        lang_tracks = [track for key, track in normalized if key == lang or key.startswith(f"{lang}-")]
        if lang_tracks:
            return prefer_ext(lang_tracks)
    return prefer_ext(tracks)


def prefer_ext(tracks: list[Track]) -> Track:
    for ext in PREFERRED_SUBTITLE_EXTENSIONS:
        found = next((track for track in tracks if (track.get("ext") or "").lower() == ext), None)
        if found:
            return found
    return tracks[0]


def fetch_subtitle(
    track: Track,
    cookie_path: str | None,
    cookie_header: str | None = None,
    platform: str = "bilibili",
) -> str:
    embedded_data = (track.get("data") or {}).get("data")
    if embedded_data:
        return str(embedded_data)

    if not track.get("url"):
        raise AppError("Selected subtitle track has neither URL nor embedded subtitle content.", status_code=422)

    headers = request_headers(platform)
    if cookie_header:
        headers["Cookie"] = cookie_header
    cookies = load_cookie_jar(cookie_path)
    with httpx.Client(follow_redirects=True, timeout=30, headers=headers, cookies=cookies) as client:
        response = client.get(track["url"])
        response.raise_for_status()
        return response.text
