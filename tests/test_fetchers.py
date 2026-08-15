"""Per-source fetch behaviour: status policy and the cache round trip.

The clients agree on one policy: 404 means "no such record" and yields an empty
result, every other non-200 raises SourceError. `request` already absorbs the
retryable statuses, so only terminal ones reach these functions.
"""

import json

import pytest

from hallubib.sources import (
    SourceError,
    arxiv,
    crossref,
    doi,
    openalex,
    semanticscholar,
)
from hallubib.types import Name

from .cassettes import Replayed

_OPENALEX_WORK = {
    "id": "https://openalex.org/W2085212829",
    "title": "College Admissions and the Stability of Marriage",
    "authorships": [{"author": {"display_name": "David Gale"}}],
    "doi": "https://doi.org/10.2307/2312726",
    "publication_year": 1962,
    "type": "article",
    "primary_location": {"source": {"display_name": "American Mathematical Monthly"}},
    "biblio": {"volume": "69", "issue": "1", "first_page": "9", "last_page": "15"},
}
_CROSSREF_ITEM = {
    "title": ["College Admissions and the Stability of Marriage"],
    "author": [{"family": "Gale", "given": "David"}],
    "issued": {"date-parts": [[1962]]},
    "container-title": ["The American Mathematical Monthly"],
    "volume": "69",
    "page": "9-15",
    "DOI": "10.2307/2312726",
    "type": "journal-article",
}
_S2_PAPER = {
    "paperId": "abc123",
    "title": "College Admissions and the Stability of Marriage",
    "authors": [{"name": "David Gale"}],
    "year": 1962,
    "journal": {"name": "The American Mathematical Monthly", "volume": "69"},
    "externalIds": {"DOI": "10.2307/2312726"},
    "publicationTypes": ["JournalArticle"],
}
_ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All You Need</title>
    <summary>Sequence transduction models.</summary>
    <author><name>Ashish Vaswani</name></author>
  </entry>
</feed>
"""


class _Fake:
    """Stand-in for `_http.request` that returns canned responses in order."""

    def __init__(self, monkeypatch, module, *responses: Replayed):
        self.responses = list(responses)
        self.calls = 0
        monkeypatch.setattr(module, "request", self)

    def __call__(self, source, url, **kwargs):
        self.calls += 1
        if not self.responses:
            raise AssertionError(f"unexpected extra request to {source}")
        return self.responses.pop(0)


def _ok(payload) -> Replayed:
    return Replayed(200, payload if isinstance(payload, str) else json.dumps(payload))


def _status(code: int) -> Replayed:
    return Replayed(code, "")


# (module, callable, args, a 200 response, the number of records it yields)
_SEARCHES = [
    pytest.param(
        openalex,
        lambda: openalex.search_title("College Admissions", 1962),
        _ok({"results": [_OPENALEX_WORK]}),
        1,
        id="openalex-title",
    ),
    pytest.param(
        crossref,
        lambda: crossref.search("College Admissions", Name(family="Gale")),
        _ok({"message": {"items": [_CROSSREF_ITEM]}}),
        1,
        id="crossref",
    ),
    pytest.param(
        semanticscholar,
        lambda: semanticscholar.search_match("College Admissions"),
        _ok({"data": [_S2_PAPER]}),
        1,
        id="semanticscholar",
    ),
    pytest.param(
        arxiv,
        lambda: arxiv.search("Attention Is All You Need"),
        _ok(_ARXIV_FEED),
        1,
        id="arxiv",
    ),
]


@pytest.mark.parametrize("module,call,response,expected", _SEARCHES)
class TestSearchPolicy:
    def test_success_parses_records(
        self, monkeypatch, module, call, response, expected
    ):
        _Fake(monkeypatch, module, response)
        records = call()
        assert len(records) == expected
        assert records[0].title

    def test_404_is_an_empty_result(
        self, monkeypatch, module, call, response, expected
    ):
        _Fake(monkeypatch, module, _status(404))
        assert call() == []

    def test_other_errors_raise(self, monkeypatch, module, call, response, expected):
        _Fake(monkeypatch, module, _status(403))
        with pytest.raises(SourceError) as exc:
            call()
        assert "403" in str(exc.value)

    def test_second_call_served_from_cache(
        self, monkeypatch, module, call, response, expected
    ):
        fake = _Fake(monkeypatch, module, response)
        first = call()
        second = call()
        assert fake.calls == 1
        assert second == first

    def test_empty_result_is_cached_too(
        self, monkeypatch, module, call, response, expected
    ):
        fake = _Fake(monkeypatch, module, _status(404))
        assert call() == []
        assert call() == []
        assert fake.calls == 1


class TestOpenAlexByDoi:
    def test_success(self, monkeypatch):
        _Fake(monkeypatch, openalex, _ok(_OPENALEX_WORK))
        rec = openalex.search_doi("10.2307/2312726")
        assert rec is not None
        assert rec.doi == "10.2307/2312726"
        assert rec.pages == "9-15"

    def test_404_is_none(self, monkeypatch):
        _Fake(monkeypatch, openalex, _status(404))
        assert openalex.search_doi("10.9999/nope") is None

    def test_other_errors_raise(self, monkeypatch):
        _Fake(monkeypatch, openalex, _status(500))
        with pytest.raises(SourceError):
            openalex.search_doi("10.1/x")

    def test_cached_hit_reparses(self, monkeypatch):
        fake = _Fake(monkeypatch, openalex, _ok(_OPENALEX_WORK))
        first = openalex.search_doi("10.2307/2312726")
        second = openalex.search_doi("10.2307/2312726")
        assert fake.calls == 1
        assert first == second

    def test_titleless_cache_entry_is_a_miss(self, monkeypatch):
        _Fake(monkeypatch, openalex, _ok({"id": "https://openalex.org/W1"}))
        assert openalex.search_doi("10.1/untitled") is None


class TestDoiValidation:
    @pytest.mark.parametrize("code", [200, 301, 302, 303, 307, 308])
    def test_resolving_statuses(self, monkeypatch, code):
        _Fake(monkeypatch, doi, _status(code))
        assert doi.validate_doi("10.1/x")

    def test_404_is_unregistered(self, monkeypatch):
        _Fake(monkeypatch, doi, _status(404))
        assert not doi.validate_doi("10.9999/nope")

    def test_other_errors_raise(self, monkeypatch):
        _Fake(monkeypatch, doi, _status(500))
        with pytest.raises(SourceError):
            doi.validate_doi("10.1/x")

    def test_verdict_is_cached(self, monkeypatch):
        fake = _Fake(monkeypatch, doi, _status(200))
        assert doi.validate_doi("10.1/cached")
        assert doi.validate_doi("10.1/cached")
        assert fake.calls == 1

    def test_negative_verdict_is_cached(self, monkeypatch):
        fake = _Fake(monkeypatch, doi, _status(404))
        assert not doi.validate_doi("10.9999/cached-miss")
        assert not doi.validate_doi("10.9999/cached-miss")
        assert fake.calls == 1


class TestSemScholarExtras:
    def test_relevance_search(self, monkeypatch):
        _Fake(monkeypatch, semanticscholar, _ok({"data": [_S2_PAPER]}))
        records = semanticscholar.search_relevance("kidney exchange", limit=5)
        assert len(records) == 1

    def test_api_key_sent_when_configured(self, monkeypatch):
        from hallubib import configure

        configure(s2_api_key="secret-key")
        seen: dict = {}

        def capture(source, url, **kwargs):
            seen.update(kwargs)
            return _ok({"data": []})

        monkeypatch.setattr(semanticscholar, "request", capture)
        semanticscholar.search_match("anything")
        assert seen["headers"] == {"x-api-key": "secret-key"}

    def test_no_header_without_key(self, monkeypatch):
        from hallubib import configure

        configure(s2_api_key=None)
        seen: dict = {}

        def capture(source, url, **kwargs):
            seen.update(kwargs)
            return _ok({"data": []})

        monkeypatch.setattr(semanticscholar, "request", capture)
        semanticscholar.search_match("anything")
        assert seen["headers"] is None


class TestArxivMalformedFeed:
    def test_unparseable_xml_raises(self, monkeypatch):
        _Fake(monkeypatch, arxiv, _ok("<feed><entry>"))
        with pytest.raises(SourceError) as exc:
            arxiv.search("Some Title")
        assert "malformed response" in str(exc.value)

    def test_author_narrows_the_query(self, monkeypatch):
        seen: dict = {}

        def capture(source, url, **kwargs):
            seen.update(kwargs["params"])
            return _ok(_ARXIV_FEED)

        monkeypatch.setattr(arxiv, "request", capture)
        arxiv.search("Attention Is All You Need", Name(family="Vaswani"))
        assert "au:vaswani" in seen["search_query"]
