from __future__ import annotations

import shutil
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from yt_dlp.utils import DownloadError

from .batch import parse_video_urls
from .config import (
    APP_TITLE,
    APP_VERSION,
    DEFAULT_ASR_MODEL,
    DEFAULT_ASR_DEVICE,
    DEFAULT_BROWSER,
    DEFAULT_ENABLE_ASR,
    DEFAULT_LANGUAGE,
    DEFAULT_PLATFORM,
    DEFAULT_SUPPRESS_HF_WARNINGS,
    STATIC_DIR,
)
from .cookies import prepare_cookie_input
from .errors import AppError
from .exports import create_result_exports
from .jobs import create_batch_extract_job, create_extract_job, get_job, job_to_dict
from .models import ExtractRequest
from .service import extract_subtitle_context, map_download_error
from .validation import browser_cookie_spec, ensure_supported_url, normalize_platform
from .ytdlp_client import download_audio


def create_app() -> FastAPI:
    application = FastAPI(title=APP_TITLE, version=APP_VERSION)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def disable_browser_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status_code=204)

    @application.post("/api/extract")
    async def extract_subtitle(
        url: str = Form(...),
        platform: str = Form(DEFAULT_PLATFORM),
        language: str = Form(DEFAULT_LANGUAGE),
        browser: str = Form(DEFAULT_BROWSER),
        enable_asr: bool = Form(DEFAULT_ENABLE_ASR),
        asr_model: str = Form(DEFAULT_ASR_MODEL),
        asr_device: str = Form(DEFAULT_ASR_DEVICE),
        hf_token: str | None = Form(None),
        suppress_hf_warnings: bool = Form(DEFAULT_SUPPRESS_HF_WARNINGS),
        cookie_text: str | None = Form(None),
        cookie_file: UploadFile | None = File(None),
    ) -> dict:
        cookie_input = prepare_cookie_input(cookie_text, cookie_file)
        request = ExtractRequest(
            url=url,
            platform=platform,
            language=language,
            browser=browser,
            enable_asr=enable_asr,
            asr_model=asr_model,
            asr_device=asr_device,
            hf_token=hf_token,
            suppress_hf_warnings=suppress_hf_warnings,
            cookie_text=cookie_text,
        )
        try:
            return extract_subtitle_context(request, cookie_input)
        except AppError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        finally:
            cookie_input.cleanup()

    @application.post("/api/extract/start")
    async def start_extract_job(
        url: str = Form(...),
        platform: str = Form(DEFAULT_PLATFORM),
        language: str = Form(DEFAULT_LANGUAGE),
        browser: str = Form(DEFAULT_BROWSER),
        enable_asr: bool = Form(DEFAULT_ENABLE_ASR),
        asr_model: str = Form(DEFAULT_ASR_MODEL),
        asr_device: str = Form(DEFAULT_ASR_DEVICE),
        hf_token: str | None = Form(None),
        suppress_hf_warnings: bool = Form(DEFAULT_SUPPRESS_HF_WARNINGS),
        cookie_text: str | None = Form(None),
        cookie_file: UploadFile | None = File(None),
    ) -> dict:
        cookie_input = prepare_cookie_input(cookie_text, cookie_file)
        request = ExtractRequest(
            url=url,
            platform=platform,
            language=language,
            browser=browser,
            enable_asr=enable_asr,
            asr_model=asr_model,
            asr_device=asr_device,
            hf_token=hf_token,
            suppress_hf_warnings=suppress_hf_warnings,
            cookie_text=cookie_text,
        )
        job = create_extract_job(request, cookie_input)
        return job_to_dict(job)

    @application.post("/api/extract/batch/start")
    async def start_batch_extract_job(
        urls: str = Form(...),
        platform: str = Form(DEFAULT_PLATFORM),
        language: str = Form(DEFAULT_LANGUAGE),
        browser: str = Form(DEFAULT_BROWSER),
        enable_asr: bool = Form(DEFAULT_ENABLE_ASR),
        asr_model: str = Form(DEFAULT_ASR_MODEL),
        asr_device: str = Form(DEFAULT_ASR_DEVICE),
        hf_token: str | None = Form(None),
        suppress_hf_warnings: bool = Form(DEFAULT_SUPPRESS_HF_WARNINGS),
        cookie_text: str | None = Form(None),
        cookie_file: UploadFile | None = File(None),
    ) -> dict:
        try:
            video_urls = parse_video_urls(urls)
        except AppError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        cookie_input = prepare_cookie_input(cookie_text, cookie_file)
        requests = [
            ExtractRequest(
                url=url,
                platform=platform,
                language=language,
                browser=browser,
                enable_asr=enable_asr,
                asr_model=asr_model,
                asr_device=asr_device,
                hf_token=hf_token,
                suppress_hf_warnings=suppress_hf_warnings,
                cookie_text=cookie_text,
            )
            for url in video_urls
        ]
        job = create_batch_extract_job(requests, cookie_input)
        return job_to_dict(job)

    @application.post("/api/audio/download")
    async def download_audio_file(
        url: str = Form(...),
        platform: str = Form(DEFAULT_PLATFORM),
        browser: str = Form(DEFAULT_BROWSER),
        cookie_text: str | None = Form(None),
        cookie_file: UploadFile | None = File(None),
    ) -> FileResponse:
        cookie_input = prepare_cookie_input(cookie_text, cookie_file)
        temp_dir = tempfile.mkdtemp(prefix="subtitle-audio-download-")
        try:
            normalized_platform = normalize_platform(platform)
            video_url = ensure_supported_url(url, normalized_platform)
            browser_cookies = browser_cookie_spec(browser)
            audio_path = download_audio(
                video_url,
                normalized_platform,
                cookie_input.path,
                browser_cookies,
                cookie_input.header,
                temp_dir,
            )
            return FileResponse(
                audio_path,
                media_type="application/octet-stream",
                filename=audio_path.name,
                background=BackgroundTask(shutil.rmtree, temp_dir, ignore_errors=True),
            )
        except AppError as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        except DownloadError as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            mapped = map_download_error(exc, normalized_platform)
            raise HTTPException(status_code=mapped.status_code, detail=mapped.message) from exc
        finally:
            cookie_input.cleanup()

    @application.get("/api/jobs/{job_id}")
    def read_job(job_id: str) -> dict:
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        return job_to_dict(job)

    @application.get("/api/jobs/{job_id}/export")
    def export_job(
        job_id: str,
        kind: str = Query("bundle", pattern="^(metadata|subtitles|bundle)$"),
        item: int | None = Query(None, ge=0),
    ) -> FileResponse:
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job.status != "completed" or not job.result:
            raise HTTPException(status_code=409, detail="The extraction job is not complete.")

        results = _completed_results(job.result)
        if item is not None:
            if item >= len(results):
                raise HTTPException(status_code=404, detail="Export result not found.")
            results = [results[item]]
        if not results:
            raise HTTPException(status_code=404, detail="No completed video result is available for export.")

        artifacts = create_result_exports(results)
        if kind == "bundle":
            if len(artifacts) != 1:
                raise HTTPException(
                    status_code=422,
                    detail="Single-video exports are available as separate metadata and subtitle files.",
                )
            artifact = artifacts[0]
        else:
            if len(results) != 1:
                raise HTTPException(status_code=422, detail="Select one video before exporting this file type.")
            suffix = ".metadata.json" if kind == "metadata" else ".subtitles.md"
            artifact = next(value for value in artifacts if value.download_name.endswith(suffix))
        return FileResponse(
            artifact.path,
            media_type=artifact.media_type,
            filename=artifact.download_name,
            background=BackgroundTask(shutil.rmtree, artifact.path.parent, ignore_errors=True),
        )

    return application


app = create_app()


def _completed_results(payload: dict) -> list[dict]:
    if "items" not in payload:
        return [payload]
    return [item["result"] for item in payload["items"] if item.get("status") == "completed" and item.get("result")]
