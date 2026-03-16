"""Disk cache for API responses under ~/.cache/hallubib/."""

import hashlib
import json
import os
import time
from pathlib import Path

DEFAULT_TTL_DAYS = 30


def _cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "hallubib"


def cache_key(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()


def get(namespace: str, key: str, ttl_days: int = DEFAULT_TTL_DAYS) -> dict | None:
    path = _cache_dir() / namespace / f"{key}.json"
    if not path.exists():
        return None
    age_days = (time.time() - path.stat().st_mtime) / 86400
    if age_days > ttl_days:
        path.unlink(missing_ok=True)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def put(namespace: str, key: str, data: dict) -> None:
    d = _cache_dir() / namespace
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{key}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def clear() -> None:
    import shutil

    d = _cache_dir()
    if d.exists():
        shutil.rmtree(d)


def cache_path() -> Path:
    return _cache_dir()
