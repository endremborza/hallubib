from hallubib.special import (
    detect_source_type,
    ignorable_supplements_for,
    is_url_only_reference,
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
