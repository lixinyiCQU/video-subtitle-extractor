from __future__ import annotations

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
        pass


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
    with YoutubeDL(ydl_options(cookie_path, browser_cookies, cookie_header, platform)) as ydl:
        info = ydl.extract_info(url, download=False)
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
    }
    if cookie_path:
        base_opts["cookiefile"] = cookie_path
    if browser_cookies:
        base_opts["cookiesfrombrowser"] = browser_cookies
    if platform == "youtube":
        base_opts["js_runtimes"] = {"node": {}}
        base_opts["remote_components"] = {"ejs:github"}

    last_error: DownloadError | None = None
    for format_selector in ASR_AUDIO_FORMATS:
        opts = {**base_opts, "format": format_selector}
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
            break
        except DownloadError as exc:
            last_error = exc
            if "Requested format is not available" not in str(exc):
                raise
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
