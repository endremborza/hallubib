"""Disk cache for API responses under ~/.cache/hallubib/."""

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from .config import get_config

_KEY_VERSION = "v2"


def _cache_dir() -> Path:
    cfg = get_config()
    if cfg.cache_dir is not None:
        return cfg.cache_dir
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "hallubib"


def cache_key(query: str) -> str:
    return hashlib.sha256(f"{_KEY_VERSION}:{query}".encode()).hexdigest()


def get(namespace: str, key: str, ttl_days: int | None = None) -> dict | None:
    if ttl_days is None:
        ttl_days = get_config().cache_ttl_days
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
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        with open(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False))
        os.replace(tmp, d / f"{key}.json")
    except OSError:
        pass


def clear() -> None:
    import shutil

    d = _cache_dir()
    if d.exists():
        shutil.rmtree(d)


def cache_path() -> Path:
    return _cache_dir()
