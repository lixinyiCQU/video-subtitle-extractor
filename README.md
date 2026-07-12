# Video Subtitle Extractor

A local or cloud GPU web application for extracting subtitles from Bilibili and YouTube videos, then formatting the result as clean AI Agent context.

The backend uses `yt-dlp` for open-source video metadata and subtitle extraction. The project provides both a local FastAPI UI and a cloud-friendly Gradio UI for Colab or other GPU servers.

## Features

- Automatic Bilibili/YouTube detection for mixed-platform URL batches
- Official and automatic subtitle support
- Automatic ASR fallback with open-source `faster-whisper` when no subtitle track exists
- Language preference selection
- Separate Bilibili and YouTube cookies in the same batch through browser cookies, raw headers, or `cookies.txt`
- Subtitle cleanup, deduplication, and timestamp normalization
- Markdown output designed for AI Agent context
- Batch extraction for up to 50 video URLs with per-video result selection
- Title-based metadata JSON and subtitle Markdown exports, packaged as ZIP for batches
- Gradio cloud UI for Google Colab or other GPU runtimes

## Local FastAPI UI

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Paste one Bilibili or YouTube URL per line in any order. The app detects each platform automatically and selects its
matching cookie input. A batch continues when an individual video fails, and the result selector switches
between completed videos without re-running extraction. Use `Metadata JSON` or `Subtitle .md` for the selected video;
when multiple videos complete, `Download ZIP` contains both files for every successful video.

## Gradio UI

```powershell
python -m pip install -r requirements.txt
python gradio_app.py --server-name 127.0.0.1 --server-port 7860
```

Open:

```text
http://127.0.0.1:7860
```

## Google Colab GPU Mode

In Colab, choose `Runtime > Change runtime type > GPU`, then run:

```python
!rm -rf /content/video-subtitle-extractor
!git clone https://github.com/lixinyiCQU/video-subtitle-extractor.git /content/video-subtitle-extractor
%cd /content/video-subtitle-extractor
!python -m pip install --upgrade -r requirements.txt
!python gradio_app.py --share --server-name 0.0.0.0 --server-port 7860
```

Gradio will print a public URL. Open that URL and use the UI entirely in the cloud runtime.

The Gradio `Video URL` tab accepts the same one-URL-per-line batch input. Select a completed title to view its output.
The export control returns two title-based files for one video, or one ZIP archive for multiple videos.

Colab preinstalls several Google packages. The project intentionally uses modern FastAPI/Starlette-compatible dependency ranges, so `--upgrade` is recommended to let pip converge on versions that work with Colab's preinstalled `google-adk`, `google-genai`, and Gradio packages.

Optional Google Drive model cache:

```python
from google.colab import drive
drive.mount('/content/drive')
import os
os.environ['HF_HOME'] = '/content/drive/MyDrive/hf_cache'
os.environ['HF_HUB_CACHE'] = '/content/drive/MyDrive/hf_cache/hub'
```

Free Colab temporary disk is usually enough for `tiny`, `base`, and `small`. Larger models such as `medium` or `large-v3` use more disk and bandwidth; Drive caching avoids re-downloading them across sessions, but if Drive space is tight, you can skip Drive and let Colab download models into temporary storage each session.

### Cloud ASR With Local Audio

YouTube may block Colab/cloud IPs from downloading audio even when the same cookies work locally. In that case, download the audio on your local machine and use the Gradio `Uploaded Audio` tab for GPU transcription.

Local audio download example:

```powershell
python -m yt_dlp -x --audio-format mp3 --cookies www.youtube.com_cookies.txt -o "%(title).200B.%(ext)s" "https://www.youtube.com/watch?v=VIDEO_ID"
```

Then upload the generated audio file in the Colab Gradio UI and choose the ASR model/device. This avoids YouTube access from Colab entirely; Colab only receives the audio file you upload and runs faster-whisper transcription.

The local FastAPI UI also includes a `Download Audio` button next to `Extract`. It detects the first URL's platform,
selects the matching browser/pasted/uploaded cookie input, and downloads the audio directly from your local machine.

## Runpod GPU Mode

Open a Jupyter Notebook in the GPU Pod and run this single cell:

```python
!if [ -d /workspace/video-subtitle-extractor/.git ]; then git -C /workspace/video-subtitle-extractor pull --ff-only; else git clone https://github.com/lixinyiCQU/video-subtitle-extractor.git /workspace/video-subtitle-extractor; fi
%cd /workspace/video-subtitle-extractor
!python -m pip install --upgrade -r requirements.txt
!python -u gradio_app.py --share --server-name 0.0.0.0 --server-port 7860 2>&1 | tee -a /workspace/video-subtitle-extractor-runpod.log
```

Gradio prints a public `gradio.live` URL when startup completes. Keep the cell running while using the service. The same
one-cell launcher is available at [runpod/launch_gradio_runpod.ipynb](runpod/launch_gradio_runpod.ipynb). Console output
is also appended to `/workspace/video-subtitle-extractor-runpod.log` for diagnosing Pod restarts. This path is outside
the cloned repository, so rerunning the one-cell launcher does not delete earlier logs.

Every batch creates `results/<timestamp>-<id>/` inside the repository. Each completed video is written immediately as
`<title>.metadata.json` and `<title>.subtitles.md`, while `manifest.json` is atomically updated after every item. When
the batch finishes, `batch-results.zip` is created in the same directory. These files do not depend on the browser or
Gradio session remaining connected. The Runpod launcher updates an existing checkout instead of deleting it, so saved
result directories survive subsequent launches.

To inspect the last diagnostic lines after a restart, run this in a separate Notebook cell:

```python
!tail -n 200 /workspace/video-subtitle-extractor-runpod.log
```

Resource lines report process RAM (`rss`), available system RAM, and GPU used/total memory around each model load,
transcription, unload, and batch item. If the log ends abruptly with memory nearly exhausted and no Python traceback,
the Pod was most likely terminated by the runtime rather than by an application exception.

On Runpod, large browser uploads can be interrupted by the proxy and show `starlette.requests.ClientDisconnect`. For large audio files, upload the file through Runpod's file tools, Jupyter file browser, `runpodctl`, `scp`, or a direct `wget` into `/workspace`, then paste that path into the Gradio `Audio file path on server` field. The Gradio UI also shows a textual `Progress` box for both the `Video URL` and `Uploaded Audio` tabs, so progress remains visible even when the platform proxy does not display Gradio's native progress indicator.

## Project Layout

```text
.
|-- app.py                         # Compatibility ASGI entrypoint
|-- gradio_app.py                  # Gradio cloud UI entrypoint
|-- colab/                         # Colab launcher notebook
|-- runpod/                        # Runpod Jupyter launcher notebook
|-- subtitle_extractor/            # Backend application package
|   |-- web.py                     # FastAPI app and HTTP routes
|   |-- service.py                 # Use-case orchestration
|   |-- batch.py                   # Shared batch parsing, progress, and partial-failure handling
|   |-- ytdlp_client.py            # yt-dlp integration and subtitle track selection
|   |-- subtitles.py               # Subtitle parsers and cleanup
|   |-- formatting.py              # AI context formatting
|   |-- exports.py                 # Metadata/subtitle files and ZIP packaging
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

The batch UI provides independent Bilibili and YouTube cookie sections. Both can be populated at the same time; cookies
are routed only to URLs detected for their platform.

Cookies are only written to a temporary file for the current request. Do not commit real cookies to version control.

In Colab mode, pasted or uploaded cookies live in the Colab runtime for the current request. They are not saved by the app unless you manually save them to Drive.

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

The first run downloads the selected model. Local CPU transcription uses `int8`; cloud GPU transcription uses CUDA with `float16` when available.

### HuggingFace Options

`faster-whisper` downloads models from HuggingFace. Anonymous downloads work, but HuggingFace may show a rate-limit warning. You can paste an optional `HF_TOKEN` in the UI to improve download reliability and speed.

On Windows, HuggingFace may also warn that symlink-based caching is unavailable. This is not fatal. The UI enables `HF_HUB_DISABLE_SYMLINKS_WARNING=1` by default for ASR jobs to hide this warning.

### Progress UI

ASR can be slow. The frontend starts a batch extraction job with `/api/extract/batch/start` and polls
`/api/jobs/{job_id}` for progress. Batch processing is sequential to avoid competing ASR workloads on one CPU/GPU.
The legacy synchronous `/api/extract` and single-job `/api/extract/start` endpoints remain available for compatibility.

## Tests

```powershell
python -m unittest discover -s tests
```

## Development Notes

New platforms should be added by extending URL validation, platform request headers, and any platform-specific subtitle filtering. The service layer should remain platform-neutral where possible.
