from __future__ import annotations

import json
import unittest

from subtitle_extractor.formatting import compact_transcript
from subtitle_extractor.models import Segment
from subtitle_extractor.subtitles import format_ts, parse_subtitle


class SubtitleParsingTests(unittest.TestCase):
    def test_parse_bilibili_json_and_merge_duplicates(self) -> None:
        raw = json.dumps(
            {
                "body": [
                    {"from": 0, "to": 1.2, "content": "  hello<br>world  "},
                    {"from": 1.2, "to": 2.4, "content": "hello<br>world"},
                    {"from": 2.4, "to": 4, "content": "next line."},
                ]
            }
        )

        segments = parse_subtitle(raw, "json")

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].text, "hello world")
        self.assertEqual(segments[0].end, 2.4)
        self.assertEqual(format_ts(segments[-1].end), "00:00:04")

    def test_parse_srt(self) -> None:
        raw = """1
00:00:00,000 --> 00:00:01,500
First line

2
00:00:01,500 --> 00:00:03,000
Second line
"""
        segments = parse_subtitle(raw, "srt")

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[1].start, 1.5)
        self.assertEqual(segments[1].text, "Second line")

    def test_compact_transcript(self) -> None:
        transcript = compact_transcript(
            [
                Segment(start=0, end=1, text="One."),
                Segment(start=1, end=2, text="Two"),
            ]
        )

        self.assertEqual(transcript, "One.\n\nTwo")


if __name__ == "__main__":
    unittest.main()
