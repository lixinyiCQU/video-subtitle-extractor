from __future__ import annotations

import re
import tempfile
from http.cookiejar import MozillaCookieJar

from fastapi import UploadFile

from .models import CookieInput


def normalize_cookie_header(value: str) -> str:
    value = value.strip()
    if value.lower().startswith("cookie:"):
        value = value.split(":", 1)[1].strip()
    return re.sub(r"\s*;\s*", "; ", value)


def looks_like_raw_cookie(value: str) -> bool:
    first_line = value.strip().splitlines()[0] if value.strip() else ""
    return "=" in first_line and "\t" not in first_line and not first_line.startswith("#")


def prepare_cookie_input(cookie_text: str | None, cookie_upload: UploadFile | None) -> CookieInput:
    raw = (cookie_text or "").strip()
    if cookie_upload and cookie_upload.filename:
        uploaded = cookie_upload.file.read()
        raw = uploaded.decode("utf-8", errors="ignore").strip()

    if not raw:
        return CookieInput()

    if cookie_text and looks_like_raw_cookie(raw) and not (cookie_upload and cookie_upload.filename):
        return CookieInput(header=normalize_cookie_header(raw))

    cookie_file = tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False)
    cookie_file.write(raw)
    cookie_file.flush()
    cookie_file.close()
    return CookieInput(temp_file=cookie_file)


def load_cookie_jar(cookie_path: str | None) -> MozillaCookieJar | None:
    if not cookie_path:
        return None
    jar = MozillaCookieJar(cookie_path)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception:
        return None
    return jar
