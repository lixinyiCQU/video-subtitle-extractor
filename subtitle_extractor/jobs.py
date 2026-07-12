from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .batch import extract_batch_context
from .errors import AppError
from .models import CookieInput, ExtractRequest
from .service import extract_subtitle_context


@dataclass
class JobState:
    id: str
    status: str = "queued"
    message: str = "Queued"
    percent: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_jobs: dict[str, JobState] = {}
_lock = threading.Lock()


def create_extract_job(request: ExtractRequest, cookie_input: CookieInput) -> JobState:
    job = JobState(id=uuid.uuid4().hex)
    with _lock:
        _jobs[job.id] = job

    thread = threading.Thread(target=_run_job, args=(job.id, request, cookie_input), daemon=True)
    thread.start()
    return job


def create_batch_extract_job(requests: list[ExtractRequest], cookie_inputs: dict[str, CookieInput]) -> JobState:
    if not requests:
        raise AppError("Provide at least one video URL.", status_code=422)
    job = JobState(id=uuid.uuid4().hex, message=f"Queued {len(requests)} videos")
    with _lock:
        _jobs[job.id] = job

    thread = threading.Thread(target=_run_batch_job, args=(job.id, requests, cookie_inputs), daemon=True)
    thread.start()
    return job


def get_job(job_id: str) -> JobState | None:
    with _lock:
        return _jobs.get(job_id)


def job_to_dict(job: JobState) -> dict[str, Any]:
    return {
        "id": job.id,
        "status": job.status,
        "message": job.message,
        "percent": job.percent,
        "result": job.result,
        "error": job.error,
        "createdAt": job.created_at,
    }


def _update(job_id: str, *, status: str | None = None, message: str | None = None, percent: int | None = None) -> None:
    with _lock:
        job = _jobs[job_id]
        if status is not None:
            job.status = status
        if message is not None:
            job.message = message
        if percent is not None:
            job.percent = max(0, min(100, percent))


def _run_job(job_id: str, request: ExtractRequest, cookie_input: CookieInput) -> None:
    def progress(message: str, percent: int) -> None:
        _update(job_id, status="running", message=message, percent=percent)

    try:
        progress("Starting extraction", 1)
        result = extract_subtitle_context(request, cookie_input, progress=progress)
        with _lock:
            job = _jobs[job_id]
            job.status = "completed"
            job.message = "Done"
            job.percent = 100
            job.result = result
    except AppError as exc:
        with _lock:
            job = _jobs[job_id]
            job.status = "failed"
            job.message = exc.message
            job.error = exc.message
    except Exception as exc:
        with _lock:
            job = _jobs[job_id]
            job.status = "failed"
            job.message = str(exc)
            job.error = str(exc)
    finally:
        cookie_input.cleanup()


def _run_batch_job(job_id: str, requests: list[ExtractRequest], cookie_inputs: dict[str, CookieInput]) -> None:
    try:
        def progress(message: str, percent: int) -> None:
            _update(job_id, status="running", message=message, percent=percent)

        result = extract_batch_context(requests, cookie_inputs, progress=progress)
        with _lock:
            job = _jobs[job_id]
            job.status = "completed"
            job.message = f"Completed {result['completed']}/{result['total']} videos"
            job.percent = 100
            job.result = result
    except Exception as exc:
        with _lock:
            job = _jobs[job_id]
            job.status = "failed"
            job.message = str(exc)
            job.error = str(exc)
    finally:
        for cookie_input in cookie_inputs.values():
            cookie_input.cleanup()
