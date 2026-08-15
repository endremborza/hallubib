"""Record and replay the HTTP layer so the full pipeline can run offline.

Interception happens at `hallubib.sources._http.request`, below the per-source
clients but above the session, so replaying exercises every fetcher's real
cache/status/parse path without a socket.
"""

import json
from pathlib import Path
from urllib.parse import urlencode

from hallubib.sources._http import SourceError

CASSETTE_DIR = Path(__file__).parent / "fixtures" / "cassettes"

# `special.validate_url` reaches for the session directly rather than going
# through `request`, so its verdicts get their own synthetic keys.
URLCHECK = "URLCHECK "


class Interaction:
    """One recorded call: either a response or the error the source raised."""

    __slots__ = ("status", "body", "error")

    def __init__(self, status: int | None, body: str, error: str | None):
        self.status = status
        self.body = body
        self.error = error

    @classmethod
    def from_dict(cls, d: dict) -> "Interaction":
        return cls(d.get("status"), d.get("body", ""), d.get("error"))

    def to_dict(self) -> dict:
        if self.error is not None:
            return {"error": self.error}
        return {"status": self.status, "body": self.body}


class Replayed:
    """The subset of requests.Response that the source clients actually use."""

    __slots__ = ("status_code", "text", "headers")

    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text
        self.headers: dict[str, str] = {}

    def json(self) -> dict:
        return json.loads(self.text)


def key(url: str, params: dict | None, method: str) -> str:
    """Stable, human-readable cassette key. Headers are excluded on purpose:
    they carry the S2 API key and must never reach a fixture file."""
    query = urlencode(sorted((k, str(v)) for k, v in (params or {}).items()))
    return f"{method} {url}?{query}" if query else f"{method} {url}"


def load(path: Path) -> dict[str, Interaction]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: Interaction.from_dict(v) for k, v in raw.items()}


def save(path: Path, interactions: dict[str, Interaction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: interactions[k].to_dict() for k in sorted(interactions)}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )


STATUSES = CASSETTE_DIR / "golden_statuses.json"


def load_statuses() -> dict[str, str]:
    return json.loads(STATUSES.read_text(encoding="utf-8"))


def save_statuses(statuses: dict[str, str]) -> None:
    STATUSES.parent.mkdir(parents=True, exist_ok=True)
    STATUSES.write_text(
        json.dumps(statuses, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def player(interactions: dict[str, Interaction]):
    """Build a stand-in for `_http.request` that serves only recorded calls."""

    def request(
        source: str,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        method: str = "GET",
        allow_redirects: bool = True,
    ) -> Replayed:
        k = key(url, params, method)
        request.calls.append(k)
        interaction = interactions.get(k)
        if interaction is None:
            raise AssertionError(
                f"no cassette entry for {k!r}\n"
                "re-record with: uv run python -m tests.record_cassettes"
            )
        if interaction.error is not None:
            raise SourceError(source, interaction.error)
        assert interaction.status is not None
        return Replayed(interaction.status, interaction.body)

    request.calls: list[str] = []
    request.interactions = interactions
    return request


def url_checker(interactions: dict[str, Interaction]):
    """Build a stand-in for `special.validate_url`."""

    def validate_url(url: str, session) -> bool:
        interaction = interactions.get(URLCHECK + url)
        if interaction is None:
            raise AssertionError(f"no cassette entry for URL check {url!r}")
        return interaction.status == 200

    return validate_url
