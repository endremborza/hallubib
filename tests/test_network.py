"""Drift canary: does each source still answer the way hallubib parses it?

Skipped unless `--run-network` is passed. These tests exist to catch the one
failure the offline suite structurally cannot see - a source changing its
schema, its matching, or its coverage under us. Run them on a schedule, not on
a pull request, so upstream flakiness never blocks a merge.

    uv run pytest tests/test_network.py -m network --run-network
"""

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import pytest

from hallubib.matching import author_last, title_similarity
from hallubib.parser import parse_file
from hallubib.sources import (
    SourceError,
    search_arxiv,
    search_crossref,
    search_openalex_doi,
    search_openalex_title,
    search_semscholar,
    search_semscholar_relevance,
    validate_doi,
)
from hallubib.types import CheckResult, Name, Status
from hallubib.verify import check_references

from . import cassettes
from .conftest import GOLDEN_BIB

pytestmark = pytest.mark.network

T = TypeVar("T")

_GS_TITLE = "College Admissions and the Stability of Marriage"


def _or_skip(fn: Callable[[], T]) -> T:
    """Any source can throttle or run out of quota - unauthenticated Semantic
    Scholar and arXiv routinely do, and OpenAlex's anonymous pool is a daily
    credit budget. That is an outage, not drift, so skip rather than fail."""
    try:
        return fn()
    except SourceError as e:
        pytest.skip(f"{e.source} unavailable: {e.detail}")


@pytest.fixture(scope="session")
def live_cache(tmp_path_factory) -> Path:
    """One cache for the whole run. Every distinct query still goes out once -
    the point is to see live responses - but no query is paid for twice."""
    return tmp_path_factory.mktemp("live-cache")


@pytest.fixture(autouse=True)
def use_live_cache(live_cache):
    from hallubib import configure

    configure(cache_dir=live_cache)


class TestDoiResolution:
    def test_registered_doi_resolves(self):
        assert _or_skip(lambda: validate_doi("10.2307/2312726"))

    def test_unregistered_doi_does_not(self):
        assert not _or_skip(lambda: validate_doi("10.9999/hallubib-not-a-real-doi"))


class TestOpenAlexSchema:
    def test_doi_lookup_still_carries_the_fields_we_read(self):
        rec = _or_skip(lambda: search_openalex_doi("10.1038/nature12373"))
        assert rec is not None
        assert rec.title
        assert rec.authors
        assert rec.year
        assert rec.ids.get("openalex", "").startswith("W")
        assert rec.type is not None

    def test_unknown_doi_is_absence_not_error(self):
        assert (
            _or_skip(lambda: search_openalex_doi("10.9999/hallubib-not-a-real-doi"))
            is None
        )

    def test_title_search_finds_a_classic(self):
        results = _or_skip(lambda: search_openalex_title(_GS_TITLE, 1962))
        assert results
        assert any(title_similarity(r.title, _GS_TITLE) > 0.9 for r in results)

    def test_year_filter_narrows(self):
        results = _or_skip(
            lambda: search_openalex_title(_GS_TITLE, 1962, with_year_filter=True)
        )
        assert results
        assert all(abs(r.year - 1962) <= 1 for r in results if r.year)

    def test_abstracts_are_still_position_inverted(self):
        results = _or_skip(
            lambda: search_openalex_title(
                "The state of OA: a large-scale analysis of the prevalence "
                "and impact of Open Access articles",
                2018,
            )
        )
        abstracts = [r.abstract for r in results if r.abstract]
        assert abstracts, "no abstract came back - has the field been renamed?"
        assert " " in abstracts[0], "de-inversion produced a single token"

    def test_invented_title_finds_nothing_close(self):
        fake = "xyzzy plugh completely fake paper title 999"
        results = _or_skip(lambda: search_openalex_title(fake, 2020))
        assert all(title_similarity(r.title, fake) < 0.3 for r in results)


class TestCrossrefSchema:
    def test_search_returns_journal_and_doi(self):
        results = _or_skip(lambda: search_crossref(_GS_TITLE, Name(family="Gale")))
        close = [r for r in results if title_similarity(r.title, _GS_TITLE) > 0.9]
        assert close
        assert any(r.journal and r.doi for r in close)

    def test_source_tag_and_type_mapping(self):
        results = _or_skip(lambda: search_crossref(_GS_TITLE))
        assert results
        assert results[0].source == "crossref"
        assert results[0].type


class TestArxivSchema:
    def test_known_preprint(self):
        results = _or_skip(
            lambda: search_arxiv("Attention Is All You Need", Name(family="Vaswani"))
        )
        assert any(
            title_similarity(r.title, "Attention Is All You Need") > 0.8
            for r in results
        )

    def test_carries_arxiv_id(self):
        results = _or_skip(lambda: search_arxiv("Attention Is All You Need"))
        if results:
            assert results[0].source == "arxiv"
            assert results[0].ids.get("arxiv")


class TestSemScholarSchema:
    def test_match_endpoint(self):
        results = _or_skip(
            lambda: search_semscholar(
                "The design of mechanisms for resource allocation",
                Name(family="Hurwicz", given="Leonid"),
            )
        )
        assert any("hurwicz" in author_last(a) for r in results for a in r.authors)

    def test_relevance_endpoint_returns_several(self):
        results = _or_skip(
            lambda: search_semscholar_relevance("kidney exchange matching market", 5)
        )
        assert len(results) > 1

    def test_invented_title_finds_nothing_close(self):
        fake = "xyzzy completely fake paper that does not exist 12345"
        results = _or_skip(lambda: search_semscholar(fake))
        assert all(title_similarity(r.title, fake) < 0.3 for r in results)


class TestGoldenBibLive:
    """The end-to-end verdicts, live, compared against what was recorded.

    A reference whose lookups degraded (a source erroring or throttling) is not
    comparable - its verdict reflects the outage, not a change upstream - so
    those are reported and skipped rather than failed.
    """

    @pytest.fixture(scope="class")
    def live(self) -> dict[str, CheckResult]:
        refs = parse_file(GOLDEN_BIB)
        return {r.reference.key: r for r in check_references(refs, max_workers=2)}

    @staticmethod
    def _degraded(result: CheckResult) -> list[str]:
        return [a.source for a in result.attempts if not a.ok]

    def test_nothing_crashed(self, live):
        assert len(live) == 12
        assert all(r.status in Status for r in live.values())

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("galeshapley62", {Status.VERIFIED, Status.AUTO_CORRECTABLE}),
            ("vaswani17", {Status.VERIFIED, Status.AUTO_CORRECTABLE}),
            ("wrongvolume", {Status.NEEDS_ATTENTION, Status.AUTO_CORRECTABLE}),
            ("deaddoi", {Status.NEEDS_ATTENTION, Status.UNKNOWN}),
            ("hallucinated", {Status.UNKNOWN}),
            ("githubrepo", {Status.URL_REFERENCE}),
            ("website", {Status.URL_REFERENCE}),
            ("deadlink", {Status.UNKNOWN}),
        ],
    )
    def test_stable_verdicts_hold(self, live, key, expected):
        result = live[key]
        if degraded := self._degraded(result):
            pytest.skip(f"{key}: lookups degraded ({', '.join(degraded)})")
        assert result.status in expected

    def test_unregistered_doi_still_called_out(self, live):
        assert any("DOI does not resolve" in n for n in live["deaddoi"].notes)

    def test_matches_the_recording(self, live):
        """A diff here means a source moved, not necessarily that hallubib
        broke. Re-record if the new verdict is right; investigate if it is
        not."""
        recorded = cassettes.load_statuses()
        drifted, degraded = {}, {}
        for key, was in recorded.items():
            now = live[key].status.value
            if was == now:
                continue
            if sources := self._degraded(live[key]):
                degraded[key] = (was, now, sources)
            else:
                drifted[key] = (was, now)
        if degraded:
            print(f"\nnot comparable, sources degraded: {degraded}")
        assert not drifted, f"verdicts drifted (recorded -> live): {drifted}"
