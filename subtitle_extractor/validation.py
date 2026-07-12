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

    host = (parsed.hostname or "").lower()
    if platform == "bilibili":
        allowed = _host_matches(host, "bilibili.com") or _host_matches(host, "bilibili.tv") or host == "b23.tv"
        if not allowed:
            raise AppError("The selected platform is Bilibili. Please enter a bilibili.com, bilibili.tv, or b23.tv URL.")
    elif platform == "youtube":
        allowed = any(_host_matches(host, domain) for domain in ("youtube.com", "youtu.be", "youtube-nocookie.com"))
        if not allowed:
            raise AppError("The selected platform is YouTube. Please enter a youtube.com or youtu.be URL.")
    else:
        raise AppError("Unsupported platform.")
    return value


def detect_platform(url: str) -> str:
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise AppError("Please enter a full http(s) video URL.")
    host = (parsed.hostname or "").lower()
    if _host_matches(host, "bilibili.com") or _host_matches(host, "bilibili.tv") or host == "b23.tv":
        return "bilibili"
    if any(_host_matches(host, domain) for domain in ("youtube.com", "youtu.be", "youtube-nocookie.com")):
        return "youtube"
    raise AppError(
        f"Unsupported video URL host '{host or 'unknown'}'. Supported platforms are Bilibili and YouTube.",
        status_code=422,
    )


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")
