from __future__ import annotations

import re
from typing import Any

from .models import Segment, Track
from .subtitles import clean_text, format_ts


def compact_transcript(segments: list[Segment]) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    current_len = 0

    for segment in segments:
        text = segment.text
        should_break = current_len >= 420 or re.search(r"[.!?]$", current[-1] if current else "")
        if current and should_break:
            paragraphs.append(" ".join(current))
            current = []
            current_len = 0
        current.append(text)
        current_len += len(text)

    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def build_ai_context(info: dict[str, Any], track: Track, segments: list[Segment], platform: str) -> str:
    title = clean_text(info.get("title") or "Untitled video")
    uploader = clean_text(info.get("uploader") or info.get("channel") or "Unknown")
    webpage_url = info.get("webpage_url") or info.get("original_url") or ""
    duration = info.get("duration")
    duration_text = format_ts(duration) if duration else "Unknown"
    platform_label = "YouTube" if platform == "youtube" else "Bilibili"

    timeline = "\n".join(f"- [{format_ts(s.start)} - {format_ts(s.end)}] {s.text}" for s in segments)
    transcript = compact_transcript(segments)

    return (
        f"# {platform_label} Video Subtitle Context\n\n"
        "## Metadata\n"
        f"- Platform: {platform_label}\n"
        f"- Title: {title}\n"
        f"- Creator: {uploader}\n"
        f"- URL: {webpage_url}\n"
        f"- Duration: {duration_text}\n"
        f"- Subtitle: {track['source']} / {track['language']} / {track['ext']}\n\n"
        "## Usage Notes\n"
        "The content below has been deduplicated and cleaned for use as AI Agent context. "
        "Use the timestamped transcript when exact source positioning matters.\n\n"
        "## Clean Transcript\n"
        f"{transcript}\n\n"
        "## Timestamped Transcript\n"
        f"{timeline}\n"
    )
