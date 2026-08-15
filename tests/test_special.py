import pytest
import requests

from hallubib import special
from hallubib.special import (
    detect_source_type,
    ignorable_supplements_for,
    is_public_url,
    is_url_only_reference,
    validate_url,
)
from hallubib.types import Reference


def _resolves_to(address: str):
    return lambda host, _port: [(0, 0, 0, "", (address, 0))]


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch: pytest.MonkeyPatch):
    """Resolve every test host to a public address: no DNS in unit tests, and the
    guard's own tests stub their own mapping."""
    monkeypatch.setattr(special.socket, "getaddrinfo", _resolves_to("93.184.216.34"))


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
    def __init__(self, status_code: int, location: str | None = None):
        self.status_code = status_code
        self.headers = {"Location": location} if location else {}
        self.is_redirect = bool(location)
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


class TestPublicUrlGuard:
    """A bibliography is untrusted input: it must not steer us onto a private
    network, directly or through a redirect."""

    def test_public_host_allowed(self):
        assert is_public_url("https://example.org/paper")

    def test_private_address_refused(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(special.socket, "getaddrinfo", _resolves_to("127.0.0.1"))
        assert not is_public_url("https://internal.example/paper")

    def test_link_local_metadata_refused(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            special.socket, "getaddrinfo", _resolves_to("169.254.169.254")
        )
        assert not is_public_url("http://169.254.169.254/latest/meta-data/")

    def test_non_http_scheme_refused(self):
        assert not is_public_url("file:///etc/passwd")
        assert not is_public_url("gopher://example.org/")

    def test_private_host_is_never_requested(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(special.socket, "getaddrinfo", _resolves_to("10.0.0.5"))
        s = _FakeSession(head=_FakeResponse(200))
        assert not validate_url("https://intranet.example/x", s)
        assert s.head_calls == 0

    def test_redirect_into_the_private_network_is_not_followed(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        hosts = {"public.example": "93.184.216.34", "intranet.example": "10.0.0.5"}
        monkeypatch.setattr(
            special.socket,
            "getaddrinfo",
            lambda host, _port: [(0, 0, 0, "", (hosts[host], 0))],
        )
        s = _FakeSession(head=_FakeResponse(302, "https://intranet.example/secret"))
        assert not validate_url("https://public.example/r", s)
        assert s.head_calls == 1
