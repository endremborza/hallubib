import pytest
import requests

from hallubib.sources import _http
from hallubib.sources._http import SourceError, request
from hallubib.sources.crossref import parse_item
from hallubib.sources.openalex import _deinvert, parse_work
from hallubib.sources.semanticscholar import parse_paper
from hallubib.types import Name


class FakeResponse:
    def __init__(self, status_code: int, headers: dict | None = None, text: str = ""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text


class FakeSession:
    def __init__(self, responses: list):
        self.responses = responses
        self.calls = 0

    def request(self, *args, **kwargs):
        self.calls += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def sleeps(monkeypatch):
    recorded: list[float] = []
    monkeypatch.setattr(_http.time, "sleep", recorded.append)
    return recorded


def _use(monkeypatch, session: FakeSession) -> None:
    monkeypatch.setattr(_http, "session", lambda: session)


class TestRetry:
    def test_retry_after_honoured(self, monkeypatch, sleeps):
        s = FakeSession([FakeResponse(429, {"Retry-After": "3"}), FakeResponse(200)])
        _use(monkeypatch, s)
        r = request("test", "https://example.org/x")
        assert r.status_code == 200
        assert s.calls == 2
        assert 3.0 in sleeps

    def test_gives_up_after_retries(self, monkeypatch, sleeps):
        s = FakeSession([FakeResponse(429), FakeResponse(429), FakeResponse(429)])
        _use(monkeypatch, s)
        with pytest.raises(SourceError) as exc:
            request("test", "https://example.org/x")
        assert "429" in str(exc.value)
        assert s.calls == 3

    def test_connection_error_raises_source_error(self, monkeypatch, sleeps):
        s = FakeSession([requests.ConnectionError("boom")] * 3)
        _use(monkeypatch, s)
        with pytest.raises(SourceError):
            request("test", "https://example.org/x")

    def test_not_found_returned_not_raised(self, monkeypatch, sleeps):
        _use(monkeypatch, FakeSession([FakeResponse(404)]))
        assert request("test", "https://example.org/x").status_code == 404


class TestOpenAlexParse:
    def test_full_work(self):
        work = {
            "id": "https://openalex.org/W2741809807",
            "title": "The state of OA",
            "authorships": [{"author": {"display_name": "Heather Piwowar"}}],
            "doi": "https://doi.org/10.7717/peerj.4375",
            "publication_year": 2018,
            "type": "article",
            "primary_location": {
                "landing_page_url": "https://peerj.com/articles/4375",
                "source": {
                    "display_name": "PeerJ",
                    "host_organization_name": "PeerJ Inc.",
                },
            },
            "biblio": {
                "volume": "6",
                "issue": None,
                "first_page": None,
                "last_page": None,
            },
            "abstract_inverted_index": {
                "Despite": [0],
                "growing": [1],
                "interest": [2],
            },
        }
        rec = parse_work(work)
        assert rec is not None
        assert rec.ids["openalex"] == "W2741809807"
        assert rec.doi == "10.7717/peerj.4375"
        assert rec.authors == [Name(family="Piwowar", given="Heather")]
        assert rec.url == "https://peerj.com/articles/4375"
        assert rec.abstract == "Despite growing interest"
        assert rec.type == "article-journal"
        assert rec.publisher == "PeerJ Inc."

    def test_deinvert_orders_positions(self):
        assert _deinvert({"b": [1], "a": [0], "c": [2]}) == "a b c"
        assert _deinvert(None) is None


class TestCrossrefParse:
    def test_full_item(self):
        item = {
            "title": ["A Paper"],
            "author": [
                {"family": "Doe", "given": "Jane"},
                {"name": "Some Consortium"},
            ],
            "issued": {"date-parts": [[2020, 5]]},
            "container-title": ["Nature"],
            "volume": "580",
            "page": "1-5",
            "DOI": "10.1038/x",
            "URL": "https://doi.org/10.1038/x",
            "type": "journal-article",
            "publisher": "Springer Nature",
            "abstract": "<jats:p>Deep thoughts.</jats:p>",
        }
        rec = parse_item(item)
        assert rec is not None
        assert rec.authors == [
            Name(family="Doe", given="Jane"),
            Name(literal="Some Consortium"),
        ]
        assert rec.type == "article-journal"
        assert rec.abstract == "Deep thoughts."
        assert rec.ids == {"doi": "10.1038/x"}
        assert rec.publisher == "Springer Nature"

    def test_no_title(self):
        assert parse_item({}) is None


class TestSemScholarParse:
    def test_parse_full(self):
        paper = {
            "paperId": "abc123",
            "title": "The Design of Mechanisms for Resource Allocation",
            "authors": [{"name": "Leonid Hurwicz"}],
            "year": 1973,
            "journal": {
                "name": "American Economic Review",
                "volume": "63",
                "pages": "1-30",
            },
            "externalIds": {"DOI": "10.1234/test", "ArXiv": "1234.5678"},
            "abstract": "We study mechanisms.",
            "url": "https://semanticscholar.org/paper/abc123",
            "publicationTypes": ["JournalArticle"],
        }
        rec = parse_paper(paper)
        assert rec is not None
        assert rec.source == "semanticscholar"
        assert rec.authors == [Name(family="Hurwicz", given="Leonid")]
        assert rec.journal == "American Economic Review"
        assert rec.ids == {
            "semanticscholar": "abc123",
            "arxiv": "1234.5678",
            "doi": "10.1234/test",
        }
        assert rec.type == "article-journal"
        assert rec.abstract == "We study mechanisms."

    def test_parse_no_title(self):
        assert parse_paper({}) is None
        assert parse_paper({"title": None}) is None

    def test_parse_minimal(self):
        rec = parse_paper({"title": "Some Paper"})
        assert rec is not None
        assert rec.authors == []
        assert rec.doi is None
        assert rec.journal is None
        assert rec.ids == {}


_ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All
  You Need</title>
    <summary>The dominant sequence transduction models are based on complex
  recurrent networks.</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <link title="doi" href="https://doi.org/10.5555/3295222"/>
  </entry>
</feed>
"""


class TestArxivParse:
    def test_parse_feed(self, monkeypatch, tmp_path):
        from hallubib.sources import arxiv

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        _use(monkeypatch, FakeSession([FakeResponse(200, text=_ARXIV_FEED)]))
        recs = arxiv.search("Attention Is All You Need", Name(family="Vaswani"))
        assert len(recs) == 1
        r = recs[0]
        assert r.title == "Attention Is All You Need"
        assert r.authors[0] == Name(family="Vaswani", given="Ashish")
        assert r.year == 2017
        assert r.ids["arxiv"] == "1706.03762v7"
        assert r.doi == "10.5555/3295222"
        assert r.url == "http://arxiv.org/abs/1706.03762v7"
        assert r.abstract is not None and r.abstract.startswith("The dominant")
        assert r.type == "article"

    def test_throttled_raises(self, monkeypatch, tmp_path):
        from hallubib.sources import arxiv

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        _use(monkeypatch, FakeSession([FakeResponse(429)] * 3))
        monkeypatch.setattr(_http.time, "sleep", lambda s: None)
        with pytest.raises(SourceError):
            arxiv.search("Some Title")


class TestOpenalexApiKey:
    def test_key_injected_only_for_openalex(self, monkeypatch):
        from hallubib import configure
        from hallubib.sources import _http

        seen: list[tuple[str, dict | None]] = []

        class FakeSession:
            def request(self, method, url, *, params, headers, timeout, allow_redirects):
                seen.append((url, params))

                class R:
                    status_code = 200

                return R()

        configure(openalex_api_key="oa-secret")
        monkeypatch.setattr(_http, "session", lambda: FakeSession())
        _http.request("openalex", "https://api.openalex.org/works", params={"search": "x"})
        _http.request("crossref", "https://api.crossref.org/works", params={"rows": 1})
        assert seen[0][1] == {"search": "x", "api_key": "oa-secret"}
        assert "api_key" not in (seen[1][1] or {})
