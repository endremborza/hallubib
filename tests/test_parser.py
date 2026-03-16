from pathlib import Path

from hallubib.parser import (
    latex_to_unicode,
    normalize_author,
    parse_bib,
    parse_file,
    split_authors,
)
from hallubib.types import EntryKind


class TestLatexToUnicode:
    def test_umlaut(self):
        assert latex_to_unicode('{\\\"o}') == "ö"

    def test_acute(self):
        assert latex_to_unicode("\\'{e}") == "é"

    def test_caron(self):
        assert latex_to_unicode("\\v{s}") == "š"

    def test_braces_stripped(self):
        assert latex_to_unicode("{NP}-completeness") == "NP-completeness"

    def test_tilde_space(self):
        assert latex_to_unicode("A~B") == "A B"

    def test_plain(self):
        assert latex_to_unicode("hello world") == "hello world"


class TestNormalizeAuthor:
    def test_first_last(self):
        assert normalize_author("David Gale") == "Gale, David"

    def test_last_first(self):
        assert normalize_author("Gale, David") == "Gale, David"

    def test_latex_accents(self):
        result = normalize_author("Farr\\'{e}, L\\'{i}dia")
        assert "Farré" in result

    def test_single_name(self):
        assert normalize_author("Aristotle") == "Aristotle"


class TestSplitAuthors:
    def test_and_split(self):
        authors = split_authors("David Gale and Lloyd S. Shapley")
        assert len(authors) == 2
        assert authors[0] == "Gale, David"
        assert authors[1] == "Shapley, Lloyd S."

    def test_others_filtered(self):
        authors = split_authors("Howden-Chapman, Philippa and others")
        assert len(authors) == 1
        assert "Howden-Chapman" in authors[0]


class TestParseBib:
    def test_inline_bib(self):
        text = """
@article{test01,
  author = {Smith, John and Doe, Jane},
  title = {A Simple Test Paper},
  journal = {Journal of Testing},
  year = {2020},
  volume = {1},
  pages = {1--10},
}
"""
        refs = parse_bib(text)
        assert len(refs) == 1
        r = refs[0]
        assert r.key == "test01"
        assert r.title == "A Simple Test Paper"
        assert r.year == 2020
        assert len(r.authors) == 2
        assert r.journal == "Journal of Testing"
        assert r.volume == "1"
        assert r.pages == "1--10"
        assert r.entry_kind == EntryKind.ARTICLE

    def test_entry_kinds_inline(self):
        text = """
@article{a, title={T1}, author={A}, year={2020}}
@book{b, title={T2}, author={B}, year={2020}}
@inproceedings{c, title={T3}, author={C}, year={2020}}
@incollection{d, title={T4}, author={D}, year={2020}}
"""
        refs = parse_bib(text)
        kinds = {r.entry_kind for r in refs}
        assert EntryKind.ARTICLE in kinds
        assert EntryKind.BOOK in kinds
        assert EntryKind.INPROCEEDINGS in kinds
        assert EntryKind.INCOLLECTION in kinds

    def test_doi_and_url(self):
        text = """
@article{withlinks,
  title = {Links Paper},
  author = {Test, A},
  year = {2021},
  doi = {10.1234/test},
  url = {https://example.com/paper},
}
"""
        refs = parse_bib(text)
        assert refs[0].doi == "10.1234/test"
        assert refs[0].url == "https://example.com/paper"

    def test_nested_braces(self):
        text = """
@article{nested,
  title = {{NP}-Completeness of {SAT}},
  author = {Cook, Stephen},
  year = {1971},
}
"""
        refs = parse_bib(text)
        assert "NP" in refs[0].title
        assert "SAT" in refs[0].title


class TestParseFile:
    def test_unsupported(self, tmp_path: Path):
        p = tmp_path / "test.txt"
        p.write_text("hello")
        try:
            parse_file(p)
            assert False, "Should have raised"
        except ValueError:
            pass
