from __future__ import annotations

import time
import traceback
from typing import Any, Callable

from .diagnostics import log_resource_snapshot
from .errors import AppError
from .models import CookieInput, ExtractRequest
from .service import extract_subtitle_context


BatchProgressCallback = Callable[[str, int], None]


def parse_video_urls(raw: str, limit: int = 50) -> list[str]:
    urls = [line.strip() for line in (raw or "").replace(",", "\n").splitlines() if line.strip()]
    if not urls:
        raise AppError("Provide at least one video URL.", status_code=422)
    if len(urls) > limit:
        raise AppError(f"A batch can contain at most {limit} video URLs.", status_code=422)
    return urls


def extract_batch_context(
    requests: list[ExtractRequest],
    cookie_input: CookieInput,
    progress: BatchProgressCallback | None = None,
) -> dict[str, Any]:
    if not requests:
        raise AppError("Provide at least one video URL.", status_code=422)

    items: list[dict[str, Any]] = []
    total = len(requests)
    print(f"[subtitle-extractor][batch] start total={total}", flush=True)
    log_resource_snapshot("batch-start")
    for index, request in enumerate(requests):
        item_number = index + 1
        started_at = time.monotonic()
        print(
            f"[subtitle-extractor][batch] video-start item={item_number}/{total} url={request.url}",
            flush=True,
        )
        log_resource_snapshot(f"video-{item_number}-start")

        def report(message: str, percent: int) -> None:
            overall = int(((index + max(0, min(100, percent)) / 100) / total) * 100)
            if progress:
                progress(f"Video {item_number}/{total}: {message}", overall)

        report("Starting extraction", 0)
        try:
            result = extract_subtitle_context(request, cookie_input, progress=report)
            items.append({"url": request.url, "status": "completed", "result": result, "error": None})
            status = "completed"
        except AppError as exc:
            items.append({"url": request.url, "status": "failed", "result": None, "error": exc.message})
            status = "failed"
            print(f"[subtitle-extractor][batch] application-error item={item_number} error={exc.message}", flush=True)
        except Exception as exc:
            items.append({"url": request.url, "status": "failed", "result": None, "error": str(exc)})
            status = "failed"
            print(f"[subtitle-extractor][batch] unexpected-error item={item_number} error={exc}", flush=True)
            traceback.print_exc()
        print(
            f"[subtitle-extractor][batch] video-end item={item_number}/{total} status={status} "
            f"elapsed={time.monotonic() - started_at:.1f}s",
            flush=True,
        )
        log_resource_snapshot(f"video-{item_number}-end")

    completed = sum(item["status"] == "completed" for item in items)
    print(f"[subtitle-extractor][batch] done completed={completed} failed={total - completed}", flush=True)
    log_resource_snapshot("batch-end")
    return {"items": items, "completed": completed, "failed": total - completed, "total": total}
