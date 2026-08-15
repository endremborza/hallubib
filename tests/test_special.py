import requests

from hallubib.special import (
    detect_source_type,
    ignorable_supplements_for,
    is_url_only_reference,
    validate_url,
)
from hallubib.types import Reference


def _make_ref(**kwargs) -> Reference:
    defaults = {
        "key": "test",
        "title": "Test",
        "authors": [],
        "type": "article-journal",
    }
    defaults.update(kwargs)
    return Reference(**defaults)


class TestDetectSourceType:
    def test_github(self):
        assert detect_source_type("https://github.com/user/repo") == "github"

    def test_arxiv(self):
        assert detect_source_type("https://arxiv.org/abs/2205.01833") == "arxiv"

    def test_website(self):
        assert detect_source_type("https://example.com") == "website"

    def test_none(self):
        assert detect_source_type(None) == "unknown"


class TestIsUrlOnly:
    def test_url_only(self):
        ref = _make_ref(url="https://example.com")
        assert is_url_only_reference(ref)

    def test_with_doi(self):
        ref = _make_ref(url="https://example.com", doi="10.1234/test")
        assert not is_url_only_reference(ref)

    def test_with_journal(self):
        ref = _make_ref(url="https://example.com", journal="Nature")
        assert not is_url_only_reference(ref)

    def test_no_url(self):
        ref = _make_ref()
        assert not is_url_only_reference(ref)

    def test_arxiv_not_url_only(self):
        ref = _make_ref(url="https://arxiv.org/abs/2205.01833")
        assert not is_url_only_reference(ref)


class TestIgnorableSupplements:
    def test_default(self):
        ignorable = ignorable_supplements_for(_make_ref())
        assert "doi" in ignorable
        assert "number" in ignorable
        assert "journal" not in ignorable

    def test_arxiv(self):
        ignorable = ignorable_supplements_for(
            _make_ref(url="https://arxiv.org/abs/1234")
        )
        assert "journal" in ignorable

    def test_book(self):
        ignorable = ignorable_supplements_for(_make_ref(type="book"))
        assert "journal" in ignorable
        assert "volume" in ignorable


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeSession:
    """Stands in for requests.Session; an Exception value is raised instead."""

    def __init__(self, head=None, get=None):
        self.head_result = head
        self.get_result = get
        self.head_calls = 0
        self.get_calls = 0

    def head(self, url, **kwargs):
        self.head_calls += 1
        return self._yield(self.head_result)

    def get(self, url, **kwargs):
        self.get_calls += 1
        return self._yield(self.get_result)

    @staticmethod
    def _yield(value):
        if isinstance(value, Exception):
            raise value
        return value


_TIMEOUT = requests.ConnectionError("timed out")


class TestValidateUrl:
    def test_head_ok(self):
        s = _FakeSession(head=_FakeResponse(200))
        assert validate_url("https://example.org/a", s)
        assert s.get_calls == 0

    def test_head_client_error(self):
        s = _FakeSession(head=_FakeResponse(404))
        assert not validate_url("https://example.org/b", s)

    def test_redirect_counts_as_reachable(self):
        assert validate_url(
            "https://example.org/c", _FakeSession(head=_FakeResponse(301))
        )

    def test_falls_back_to_get_when_head_fails(self):
        s = _FakeSession(head=_TIMEOUT, get=_FakeResponse(200))
        assert validate_url("https://example.org/d", s)
        assert s.get_calls == 1

    def test_get_response_is_closed(self):
        body = _FakeResponse(200)
        validate_url("https://example.org/e", _FakeSession(head=_TIMEOUT, get=body))
        assert body.closed

    def test_both_methods_failing_is_unreachable(self):
        s = _FakeSession(head=_TIMEOUT, get=_TIMEOUT)
        assert not validate_url("https://example.org/f", s)

    def test_result_is_cached(self):
        s = _FakeSession(head=_FakeResponse(200))
        assert validate_url("https://example.org/g", s)
        assert validate_url("https://example.org/g", s)
        assert s.head_calls == 1

    def test_unreachable_result_is_cached_too(self):
        s = _FakeSession(head=_TIMEOUT, get=_TIMEOUT)
        assert not validate_url("https://example.org/h", s)
        assert not validate_url("https://example.org/h", s)
        assert s.head_calls == 1
