"""Round-trip fidelity: golden.bib -> to_csl -> to_bib -> parse_bib."""

import pytest

from hallubib.bib import to_bib
from hallubib.csl import to_csl
from hallubib.parser import parse_bib
from hallubib.types import Reference

from .conftest import GOLDEN_BIB

_SCALAR_FIELDS = ("title", "year", "journal", "volume", "number", "pages", "doi", "url")


@pytest.fixture(scope="module")
def source_refs() -> list[Reference]:
    return parse_bib(GOLDEN_BIB.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def regenerated(source_refs) -> str:
    return to_bib([to_csl(r) for r in source_refs])


def _field_set(ref: Reference) -> set[str]:
    fields = {
        f
        for f in _SCALAR_FIELDS
        if getattr(ref, f) is not None and getattr(ref, f) != ""
    }
    if ref.authors:
        fields.add("authors")
    return fields | set(ref.extra)


class TestRoundTrip:
    def test_all_entries_survive(self, source_refs, regenerated):
        assert len(parse_bib(regenerated)) == len(source_refs)

    def test_no_field_is_lost_or_invented(self, source_refs, regenerated):
        new = {r.key: r for r in parse_bib(regenerated)}
        for old in source_refs:
            assert _field_set(old) == _field_set(new[old.key]), old.key

    def test_scalar_values_preserved(self, source_refs, regenerated):
        new = {r.key: r for r in parse_bib(regenerated)}
        for old in source_refs:
            n = new[old.key]
            for f in _SCALAR_FIELDS:
                assert getattr(old, f) == getattr(n, f), f"{old.key}.{f}"

    def test_types_preserved(self, source_refs, regenerated):
        new = {r.key: r for r in parse_bib(regenerated)}
        for old in source_refs:
            assert old.type == new[old.key].type, old.key

    def test_author_structure_preserved(self, source_refs, regenerated):
        new = {r.key: r for r in parse_bib(regenerated)}
        for old in source_refs:
            n = new[old.key]
            assert [(a.family, a.given, a.literal) for a in old.authors] == [
                (a.family, a.given, a.literal) for a in n.authors
            ], old.key

    def test_accented_names_survive(self, source_refs, regenerated):
        new = {r.key: r for r in parse_bib(regenerated)}
        families = [a.family for a in new["wrongyear"].authors]
        assert "Sönmez" in families
        assert "Ünver" in families

    def test_second_pass_is_a_fixpoint(self, regenerated):
        twice = to_bib([to_csl(r) for r in parse_bib(regenerated)])
        assert regenerated == twice


class TestCslShape:
    def test_every_entry_has_id_and_type(self, source_refs):
        for r in source_refs:
            csl = to_csl(r)
            assert csl["id"] == r.key
            assert csl["type"]

    def test_page_ranges_pass_through_verbatim(self, source_refs):
        """CSL keeps the source's dash style so the bib writer round-trips;
        `verify._compute_diffs` is where dash variants get normalized away."""
        by_key = {r.key: to_csl(r) for r in source_refs}
        assert by_key["galeshapley62"]["page"] == "9--15"

    def test_structured_names_not_flattened(self, source_refs):
        authors = to_csl(source_refs[0])["author"]
        assert authors[0] == {"family": "Gale", "given": "David"}


class TestBraceSafety:
    """A stray brace in a value closes the entry early and corrupts the rest of
    the file; matched braces (protected capitals, `{\\LaTeX}`) must survive."""

    def _item(self, title: str) -> dict:
        return {"id": "k", "type": "article-journal", "title": title}

    def test_unmatched_closing_brace_is_escaped(self):
        bib = to_bib([self._item("Effects of }} on parsing"), self._item("Second")])
        parsed = parse_bib(bib)
        assert [r.key for r in parsed] == ["k", "k"]
        assert parsed[1].title == "Second"

    def test_unmatched_opening_brace_is_escaped(self):
        parsed = parse_bib(to_bib([self._item("A { dangling brace")]))
        assert len(parsed) == 1

    def test_matched_braces_pass_through(self):
        bib = to_bib([self._item("The {DNA} of {\\LaTeX}")])
        assert "{The {DNA} of {\\LaTeX}}" in bib

    def test_trailing_backslash_cannot_escape_the_closing_brace(self):
        parsed = parse_bib(to_bib([self._item("Path C:\\"), self._item("Second")]))
        assert len(parsed) == 2
