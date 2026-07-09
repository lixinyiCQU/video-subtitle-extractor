# Architecture

The application is intentionally split into small, platform-aware modules while keeping the public HTTP API stable.

## Layers

- `web.py`: FastAPI construction, route definitions, multipart form handling, and error mapping.
- `gradio_ui.py`: Cloud-friendly Gradio interface for Colab and GPU servers.
- `service.py`: Application use case. It validates inputs, invokes extraction, parses subtitles, and shapes the response.
- `jobs.py`: In-memory background job runner used by the frontend progress UI.
- `ytdlp_client.py`: Integration boundary for `yt-dlp`, including subtitle track collection and preference rules.
- `asr.py`: Audio transcription fallback using open-source `faster-whisper`.
- `subtitles.py`: Pure parsing and normalization logic for JSON, SRT, VTT, ASS, and TTML.
- `formatting.py`: Output formatting for AI Agent context.
- `cookies.py`: Cookie upload, temporary file handling, raw header normalization, and cookie jar loading.
- `validation.py`: Platform and URL validation.
- `http_headers.py`: Request headers by platform.

## Extension Points

To add a new platform:

1. Add the platform key in `config.py`.
2. Extend `ensure_supported_url` in `validation.py`.
3. Add platform headers in `http_headers.py` when needed.
4. Add filtering or track preference logic in `ytdlp_client.py` only if the generic logic is not enough.
5. Add one or more tests in `tests/`.

The frontend sends a generic `platform` field, so additional platforms can share the same endpoint.

## UI Entrypoints

- `app.py` launches the local FastAPI/static UI.
- `gradio_app.py` launches a Gradio UI designed for Colab and other cloud GPU runtimes.

Both entrypoints use the same `service.py` extraction pipeline.

For YouTube, `ytdlp_client.py` enables Node.js as a JavaScript runtime and allows `remote_components={"ejs:github"}` so `yt-dlp` can solve current YouTube JavaScript challenges when needed.

## Subtitle Fallback Flow

1. `yt-dlp` extracts video metadata.
2. The app collects official and automatic subtitle tracks.
3. If a usable subtitle exists, the app downloads/parses it.
4. If no subtitle exists and ASR fallback is enabled, `yt-dlp` downloads audio into a temporary directory.
5. `faster-whisper` transcribes the audio into timestamped segments.
6. The same formatter builds AI Agent context for both native subtitles and ASR output.

## Progress Flow

The synchronous `/api/extract` endpoint remains available. The browser uses the background job flow:

1. `POST /api/extract/start` creates an in-memory job and starts a daemon worker thread.
2. The worker reports coarse progress stages such as metadata, subtitle parsing, audio download, model loading, and transcription.
3. The frontend polls `GET /api/jobs/{job_id}` until the job is completed or failed.

This is intentionally simple for local desktop use. For multi-user deployment, replace `jobs.py` with a persistent queue such as Redis Queue, Celery, Dramatiq, or a database-backed task table.
