"""Parser assertions over the committed golden bibliography.

tests/test_parser.py covers the grammar on synthetic input; this file pins what
the parser makes of a whole realistic file, so a regression shows up as a
changed reference rather than a changed token.
"""

import pytest

from hallubib.parser import parse_bib, parse_file
from hallubib.types import Reference

from .conftest import GOLDEN_BIB


@pytest.fixture(scope="module")
def refs() -> list[Reference]:
    return parse_bib(GOLDEN_BIB.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def by_key(refs) -> dict[str, Reference]:
    return {r.key: r for r in refs}


class TestStructure:
    def test_entry_count(self, refs):
        assert len(refs) == 12

    def test_keys_are_unique(self, refs):
        keys = [r.key for r in refs]
        assert len(keys) == len(set(keys))

    def test_comments_are_not_entries(self, refs):
        assert all(not r.key.startswith("%") for r in refs)

    def test_every_entry_has_a_title(self, refs):
        for r in refs:
            assert r.title, r.key

    def test_every_entry_has_an_author(self, refs):
        for r in refs:
            assert r.authors, r.key

    def test_parse_file_dispatches_on_suffix(self):
        assert len(parse_file(GOLDEN_BIB)) == 12


class TestTypeMapping:
    @pytest.mark.parametrize(
        "key,expected",
        [
            ("galeshapley62", "article-journal"),
            ("mascolell95", "book"),
            ("roth08", "chapter"),
            ("githubrepo", "document"),
        ],
    )
    def test_bibtex_type_becomes_csl_type(self, by_key, key, expected):
        assert by_key[key].type == expected

    def test_books_have_no_journal(self, refs):
        for r in refs:
            if r.type == "book":
                assert r.journal is None, r.key


class TestFieldExtraction:
    def test_full_article(self, by_key):
        gs = by_key["galeshapley62"]
        assert gs.title == "College Admissions and the Stability of Marriage"
        assert gs.year == 1962
        assert gs.journal == "The American Mathematical Monthly"
        assert (gs.volume, gs.number, gs.pages) == ("69", "1", "9--15")
        assert gs.doi == "10.2307/2312726"

    def test_authors_split_on_and(self, by_key):
        assert [a.family for a in by_key["mascolell95"].authors] == [
            "Mas-Colell",
            "Whinston",
            "Green",
        ]

    def test_hyphenated_family_name_kept_whole(self, by_key):
        assert by_key["mascolell95"].authors[0].family == "Mas-Colell"

    def test_latex_accents_decoded(self, by_key):
        families = [a.family for a in by_key["wrongyear"].authors]
        assert families == ["Roth", "Sönmez", "Ünver"]

    def test_corporate_author_kept_literal(self, by_key):
        author = by_key["githubrepo"].authors[0]
        assert author.literal == "OurResearch"
        assert not author.family

    def test_url_field_extracted(self, by_key):
        assert by_key["vaswani17"].url == "https://arxiv.org/abs/1706.03762"

    def test_unmodelled_fields_kept_in_extra(self, by_key):
        assert by_key["mascolell95"].extra["publisher"] == "Oxford University Press"

    def test_raw_field_body_retained(self, by_key):
        raw = by_key["galeshapley62"].raw
        assert raw.startswith("title = {College Admissions")
        assert "doi = {10.2307/2312726}" in raw


class TestLatexCommandsInPreservedFields:
    def test_url_command_is_not_read_as_an_accent(self, by_key):
        assert by_key["githubrepo"].extra["howpublished"] == (
            r"\urlhttps://github.com/ourresearch/openalex-guts"
        )
