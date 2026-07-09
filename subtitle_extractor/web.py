from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import (
    APP_TITLE,
    APP_VERSION,
    DEFAULT_ASR_MODEL,
    DEFAULT_BROWSER,
    DEFAULT_ENABLE_ASR,
    DEFAULT_LANGUAGE,
    DEFAULT_PLATFORM,
    DEFAULT_SUPPRESS_HF_WARNINGS,
    STATIC_DIR,
)
from .cookies import prepare_cookie_input
from .errors import AppError
from .jobs import create_extract_job, get_job, job_to_dict
from .models import ExtractRequest
from .service import extract_subtitle_context


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
            hf_token=hf_token,
            suppress_hf_warnings=suppress_hf_warnings,
            cookie_text=cookie_text,
        )
        job = create_extract_job(request, cookie_input)
        return job_to_dict(job)

    @application.get("/api/jobs/{job_id}")
    def read_job(job_id: str) -> dict:
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        return job_to_dict(job)

    return application


app = create_app()
