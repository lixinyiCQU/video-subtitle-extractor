from __future__ import annotations

from typing import Any, Callable

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
    for index, request in enumerate(requests):
        item_number = index + 1

        def report(message: str, percent: int) -> None:
            overall = int(((index + max(0, min(100, percent)) / 100) / total) * 100)
            if progress:
                progress(f"Video {item_number}/{total}: {message}", overall)

        report("Starting extraction", 0)
        try:
            result = extract_subtitle_context(request, cookie_input, progress=report)
            items.append({"url": request.url, "status": "completed", "result": result, "error": None})
        except AppError as exc:
            items.append({"url": request.url, "status": "failed", "result": None, "error": exc.message})
        except Exception as exc:
            items.append({"url": request.url, "status": "failed", "result": None, "error": str(exc)})

    completed = sum(item["status"] == "completed" for item in items)
    return {"items": items, "completed": completed, "failed": total - completed, "total": total}
