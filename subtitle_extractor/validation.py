from __future__ import annotations

from urllib.parse import urlparse

from .config import DEFAULT_BROWSER, DEFAULT_PLATFORM, SUPPORTED_BROWSERS, SUPPORTED_PLATFORMS
from .errors import AppError


def normalize_platform(platform: str | None) -> str:
    value = (platform or DEFAULT_PLATFORM).strip().lower()
    if value not in SUPPORTED_PLATFORMS:
        raise AppError("Platform must be either 'bilibili' or 'youtube'.")
    return value


def normalize_browser(browser: str | None) -> str:
    value = (browser or DEFAULT_BROWSER).strip().lower()
    if value not in SUPPORTED_BROWSERS:
        raise AppError("Browser cookie source must be one of: none, chrome, edge, firefox.")
    return value


def browser_cookie_spec(browser: str | None) -> tuple[str, str | None, str | None, str | None] | None:
    value = normalize_browser(browser)
    if value == "none":
        return None
    return (value, None, None, None)


def ensure_supported_url(url: str, platform: str) -> str:
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise AppError("Please enter a full http(s) video URL.")

    host = parsed.netloc.lower()
    if platform == "bilibili":
        allowed = host.endswith("bilibili.com") or host.endswith("bilibili.tv") or host == "b23.tv"
        if not allowed:
            raise AppError("The selected platform is Bilibili. Please enter a bilibili.com, bilibili.tv, or b23.tv URL.")
    elif platform == "youtube":
        allowed = host.endswith("youtube.com") or host.endswith("youtu.be") or host.endswith("youtube-nocookie.com")
        if not allowed:
            raise AppError("The selected platform is YouTube. Please enter a youtube.com or youtu.be URL.")
    else:
        raise AppError("Unsupported platform.")
    return value
