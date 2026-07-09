from __future__ import annotations

import html
import json
import re

from .errors import AppError
from .models import Segment


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("\u200b", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_language_key(key: str) -> str:
    return key.lower().replace("_", "-")


def format_ts(seconds: float) -> str:
    seconds = max(float(seconds or 0), 0)
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d}"


def parse_json_subtitle(raw: str) -> list[Segment]:
    data = json.loads(raw)
    body = data.get("body") if isinstance(data, dict) else None
    if not isinstance(body, list):
        raise ValueError("not a bilibili json subtitle")

    segments: list[Segment] = []
    for item in body:
        text = clean_text(str(item.get("content") or ""))
        if not text:
            continue
        start = float(item.get("from") or item.get("start") or 0)
        end = float(item.get("to") or item.get("end") or start)
        segments.append(Segment(start=start, end=end, text=text))
    return segments


def parse_srt_timestamp(value: str) -> float:
    match = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", value.strip())
    if not match:
        return 0
    hours, minutes, seconds, millis = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis[:3].ljust(3, "0")) / 1000


def parse_vtt_or_srt(raw: str) -> list[Segment]:
    raw = raw.replace("\ufeff", "").replace("\r\n", "\n")
    blocks = re.split(r"\n{2,}", raw.strip())
    segments: list[Segment] = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or lines[0].upper().startswith("WEBVTT"):
            continue
        if lines[0].isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue

        start_raw, end_raw = [part.strip().split(" ")[0] for part in lines[0].split("-->", 1)]
        text = clean_text("\n".join(lines[1:]))
        if text:
            segments.append(Segment(start=parse_srt_timestamp(start_raw), end=parse_srt_timestamp(end_raw), text=text))
    return segments


def parse_ass(raw: str) -> list[Segment]:
    segments: list[Segment] = []
    format_fields: list[str] = []

    for line in raw.replace("\r\n", "\n").splitlines():
        if line.startswith("Format:"):
            format_fields = [part.strip().lower() for part in line.removeprefix("Format:").split(",")]
            continue
        if not line.startswith("Dialogue:"):
            continue

        payload = line.removeprefix("Dialogue:").strip()
        if not format_fields:
            parts = payload.split(",", 9)
            start_raw, end_raw, text_raw = parts[1], parts[2], parts[-1] if len(parts) >= 10 else ""
        else:
            parts = payload.split(",", len(format_fields) - 1)
            row = dict(zip(format_fields, parts))
            start_raw = row.get("start", "0:00:00.00")
            end_raw = row.get("end", "0:00:00.00")
            text_raw = row.get("text", "")
        text = re.sub(r"\{[^}]+\}", "", text_raw).replace("\\N", "\n")
        text = clean_text(text)
        if text:
            segments.append(Segment(start=parse_srt_timestamp(start_raw), end=parse_srt_timestamp(end_raw), text=text))
    return segments


def parse_ttml(raw: str) -> list[Segment]:
    segments: list[Segment] = []
    pattern = re.compile(
        r"<p[^>]*begin=\"(?P<begin>[^\"]+)\"[^>]*(?:end=\"(?P<end>[^\"]+)\"|dur=\"(?P<dur>[^\"]+)\")[^>]*>(?P<text>.*?)</p>",
        flags=re.I | re.S,
    )
    for match in pattern.finditer(raw):
        start = parse_ttml_time(match.group("begin"))
        end = parse_ttml_time(match.group("end")) if match.group("end") else start + parse_ttml_time(match.group("dur"))
        text = clean_text(match.group("text"))
        if text:
            segments.append(Segment(start=start, end=end, text=text))
    return segments


def parse_ttml_time(value: str) -> float:
    value = value.strip()
    if value.endswith("s"):
        return float(value[:-1])
    return parse_srt_timestamp(value.replace(".", ","))


def parse_subtitle(raw: str, ext: str) -> list[Segment]:
    ext = (ext or "").lower()
    if ext == "json":
        parsers = [parse_json_subtitle, parse_vtt_or_srt, parse_ttml, parse_ass]
    elif ext in {"vtt", "srt"}:
        parsers = [parse_vtt_or_srt, parse_json_subtitle, parse_ttml, parse_ass]
    elif ext == "ass":
        parsers = [parse_ass, parse_vtt_or_srt, parse_json_subtitle, parse_ttml]
    elif ext in {"ttml", "srv1", "srv2", "srv3"}:
        parsers = [parse_ttml, parse_vtt_or_srt, parse_json_subtitle, parse_ass]
    else:
        parsers = [parse_json_subtitle, parse_vtt_or_srt, parse_ttml, parse_ass]

    last_error: Exception | None = None
    for parser in parsers:
        try:
            segments = parser(raw)
            if segments:
                return merge_segments(segments)
        except Exception as exc:
            last_error = exc
    raise AppError(f"Unable to parse subtitle content: {last_error or 'unknown subtitle format'}", status_code=422)


def merge_segments(segments: list[Segment]) -> list[Segment]:
    merged: list[Segment] = []
    for segment in sorted(segments, key=lambda item: item.start):
        text = clean_text(segment.text)
        if not text:
            continue
        if merged and text == merged[-1].text:
            merged[-1].end = max(merged[-1].end, segment.end)
            continue
        merged.append(Segment(start=segment.start, end=max(segment.end, segment.start), text=text))
    return merged
