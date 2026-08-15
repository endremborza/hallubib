"""Global, injectable configuration replacing hardcoded session/cache settings."""

import os
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Config:
    mailto: str | None = None
    cache_dir: Path | None = None
    cache_ttl_days: int = 30
    timeout: float = 15.0
    max_workers: int = 6
    s2_api_key: str | None = None


def _from_env() -> Config:
    return Config(
        mailto=os.environ.get("HALLUBIB_MAILTO"),
        s2_api_key=os.environ.get("S2_API_KEY"),
    )


_config = _from_env()
_generation = 0


def configure(**overrides) -> Config:
    global _config, _generation
    if "cache_dir" in overrides and overrides["cache_dir"] is not None:
        overrides["cache_dir"] = Path(overrides["cache_dir"])
    _config = replace(_config, **overrides)
    _generation += 1
    return _config


def get_config() -> Config:
    return _config


def generation() -> int:
    return _generation
