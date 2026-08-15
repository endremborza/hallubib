"""Record HTTP fixtures for the offline replay suite. Needs network.

    uv run python -m tests.record_cassettes

Runs the full pipeline over tests/fixtures/golden.bib against the live APIs and
writes every interaction to tests/fixtures/cassettes/golden.json. A cold cache
directory is used so no call is served from a previous run's cache.

Any call that ends in a SourceError is recorded as an error and reported at the
end; re-run to fill those in once the throttling source recovers.
"""

import sys
import tempfile
from pathlib import Path

from hallubib import configure
from hallubib.parser import parse_file
from hallubib.sources import _http
from hallubib.verify import check_references

from . import cassettes
from .cassettes import CASSETTE_DIR, Interaction

GOLDEN_BIB = Path(__file__).parent / "fixtures" / "golden.bib"


def record() -> int:
    import hallubib.special as special
    import hallubib.verify as verify

    interactions: dict[str, Interaction] = {}
    real_request = _http.request
    real_validate_url = special.validate_url

    def recording_request(source, url, *, params=None, **kwargs):
        method = kwargs.get("method", "GET")
        key = cassettes.key(url, params, method)
        try:
            response = real_request(source, url, params=params, **kwargs)
        except Exception as e:
            detail = getattr(e, "detail", str(e))
            interactions[key] = Interaction(None, "", detail)
            raise
        interactions[key] = Interaction(response.status_code, response.text, None)
        return response

    def recording_validate_url(url, session):
        reachable = real_validate_url(url, session)
        interactions[cassettes.URLCHECK + url] = Interaction(
            200 if reachable else 404, "", None
        )
        return reachable

    _http.request = recording_request
    special.validate_url = recording_validate_url
    verify.validate_url = recording_validate_url
    for module in ("arxiv", "crossref", "doi", "openalex", "semanticscholar"):
        mod = __import__(f"hallubib.sources.{module}", fromlist=["request"])
        if hasattr(mod, "request"):
            mod.request = recording_request

    with tempfile.TemporaryDirectory(prefix="hallubib-record-") as cold_cache:
        configure(cache_dir=cold_cache)
        refs = parse_file(GOLDEN_BIB)
        print(f"recording {len(refs)} references from {GOLDEN_BIB.name}")
        results = check_references(refs, max_workers=2)

    for r in sorted(results, key=lambda r: r.reference.key):
        print(f"  {r.reference.key:<16s} {r.status.value}")
    cassettes.save_statuses({r.reference.key: r.status.value for r in results})

    out = CASSETTE_DIR / "golden.json"
    merged = cassettes.load(out) if out.exists() else {}
    for k, fresh in interactions.items():
        # a throttled retry must never demote an interaction we already have
        if fresh.error and merged.get(k) and not merged[k].error:
            continue
        merged[k] = fresh
    cassettes.save(out, merged)
    failed = [k for k, i in merged.items() if i.error]
    total = len(merged)
    print(f"\nwrote {total} interactions to {out.relative_to(Path.cwd())}")
    if failed:
        print(f"\n{len(failed)} call(s) recorded as errors - re-run to fill in:")
        for k in failed:
            print(f"  {interactions[k].error}  <-  {k}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(record())
