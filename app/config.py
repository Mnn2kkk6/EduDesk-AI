"""Central configuration loaded from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def _path_from_env(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    path = Path(raw) if raw else default
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


DATA_DIR = ROOT_DIR / "data"
KNOWLEDGE_DIR = ROOT_DIR / "data" / "knowledge_base"
UPLOAD_DIR = _path_from_env("EDUDESK_UPLOAD_DIR", DATA_DIR / "uploads")
DB_PATH = _path_from_env("EDUDESK_DB_PATH", DATA_DIR / "edudeska i.db".replace(" ", ""))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()
API_URL = os.getenv("EDUDESK_API_URL", "http://127.0.0.1:8000").rstrip("/")

try:
    MAX_UPLOAD_BYTES = max(1, int(os.getenv("EDUDESK_MAX_UPLOAD_MB", "10"))) * 1024 * 1024
except ValueError:
    MAX_UPLOAD_BYTES = 10 * 1024 * 1024
