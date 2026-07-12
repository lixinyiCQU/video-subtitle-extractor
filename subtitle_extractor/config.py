from __future__ import annotations

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
STATIC_DIR = PROJECT_ROOT / "static"

APP_TITLE = "Video Subtitle Extractor"
APP_VERSION = "1.8.1"

SUPPORTED_PLATFORMS = frozenset({"bilibili", "youtube"})
SUPPORTED_BROWSERS = frozenset({"none", "chrome", "edge", "firefox"})

DEFAULT_PLATFORM = "bilibili"
DEFAULT_LANGUAGE = "auto"
DEFAULT_BROWSER = "none"
DEFAULT_ENABLE_ASR = True
DEFAULT_ASR_MODEL = "base"
DEFAULT_ASR_DEVICE = "auto"
DEFAULT_SUPPRESS_HF_WARNINGS = True

SUBTITLE_FORMATS = "json/srt/vtt/ass/best"
ASR_AUDIO_FORMATS = (
    "bestaudio/best",
    "ba/b",
    "best[acodec!=none]/best",
    "worst[acodec!=none]/worst",
)
ASR_SUPPORTED_MODELS = ("tiny", "base", "small", "medium", "large-v3")
ASR_SUPPORTED_DEVICES = ("auto", "cpu", "cuda")
PREFERRED_SUBTITLE_EXTENSIONS = ("json", "srt", "vtt", "ass", "ttml")
PREFERRED_LANGUAGES = (
    "zh-hans",
    "zh-cn",
    "zh-hant",
    "zh-tw",
    "zh",
    "zh-hans-orig",
    "zh-hant-orig",
    "en",
    "en-orig",
    "ja",
)
