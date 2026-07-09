# Video Subtitle Extractor

A local web application for extracting subtitles from Bilibili and YouTube videos, then formatting the result as clean AI Agent context.

The backend uses `yt-dlp` for open-source video metadata and subtitle extraction. The frontend is a lightweight static UI served by FastAPI.

## Features

- Platform switcher for Bilibili and YouTube
- Official and automatic subtitle support
- Automatic ASR fallback with open-source `faster-whisper` when no subtitle track exists
- Language preference selection
- Cookie support through browser cookies, raw `Cookie:` headers, or Netscape `cookies.txt`
- Subtitle cleanup, deduplication, and timestamp normalization
- Markdown output designed for AI Agent context

## Quick Start

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Project Layout

```text
.
|-- app.py                         # Compatibility ASGI entrypoint
|-- subtitle_extractor/            # Backend application package
|   |-- web.py                     # FastAPI app and HTTP routes
|   |-- service.py                 # Use-case orchestration
|   |-- ytdlp_client.py            # yt-dlp integration and subtitle track selection
|   |-- subtitles.py               # Subtitle parsers and cleanup
|   |-- formatting.py              # AI context formatting
|   |-- cookies.py                 # Cookie file/header handling
|   |-- validation.py              # Platform, browser, and URL validation
|   |-- http_headers.py            # Per-platform request headers
|   |-- models.py                  # Shared dataclasses and type aliases
|   |-- config.py                  # Constants and paths
|   `-- errors.py                  # Application-level errors
|-- static/                        # Static frontend
|-- tests/                         # Unit tests
|-- requirements.txt               # Runtime dependencies
|-- pyproject.toml                 # Project metadata and tool configuration
`-- README.md
```

## Cookie Notes

Public videos usually do not need cookies. Cookies may be required for logged-in content, age-gated videos, regional restrictions, or Bilibili HTTP 412 anti-bot responses.

YouTube may also return `Sign in to confirm you're not a bot`. In that case, log in to YouTube in your browser and provide cookies through the UI. ASR fallback cannot bypass this check because audio download also requires video metadata access.

Supported cookie inputs:

- Read cookies from Edge, Chrome, or Firefox
- Paste a raw `Cookie: ...` request header
- Upload a Netscape-format `cookies.txt`

Cookies are only written to a temporary file for the current request. Do not commit real cookies to version control.

For YouTube, some videos may show `Sign in to confirm you're not a bot` or `Requested format is not available`. In practice, both usually mean YouTube did not expose downloadable formats to the anonymous request. Log in to YouTube and provide browser cookies or a YouTube `cookies.txt` file.

The app enables Node.js as the `yt-dlp` JavaScript runtime for YouTube and allows the recommended `ejs:github` challenge solver component. This helps `yt-dlp` recover formats that YouTube hides behind JavaScript challenges.

## ASR Fallback

When a video has no extractable subtitle track, the app can download the best available audio stream and transcribe it with `faster-whisper`.

The UI enables this fallback by default. Available models:

- `tiny`: fastest, lowest quality
- `base`: default balance
- `small`: better quality, slower
- `medium`: much slower
- `large-v3`: best quality, slowest and most resource intensive

The first run downloads the selected model. CPU transcription works with `compute_type=int8`; long videos can still take time.

### HuggingFace Options

`faster-whisper` downloads models from HuggingFace. Anonymous downloads work, but HuggingFace may show a rate-limit warning. You can paste an optional `HF_TOKEN` in the UI to improve download reliability and speed.

On Windows, HuggingFace may also warn that symlink-based caching is unavailable. This is not fatal. The UI enables `HF_HUB_DISABLE_SYMLINKS_WARNING=1` by default for ASR jobs to hide this warning.

### Progress UI

ASR can be slow. The frontend now starts an extraction job with `/api/extract/start` and polls `/api/jobs/{job_id}` for progress. The legacy synchronous `/api/extract` endpoint is still available for compatibility.

## Tests

```powershell
python -m unittest discover -s tests
```

## Development Notes

New platforms should be added by extending URL validation, platform request headers, and any platform-specific subtitle filtering. The service layer should remain platform-neutral where possible.
