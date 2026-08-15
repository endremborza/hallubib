from pathlib import Path

from hallubib.names import latex_to_unicode, parse_name, split_authors
from hallubib.parser import parse_bib, parse_bibitem, parse_file, parse_tex
from hallubib.types import Name


class TestLatexToUnicode:
    def test_umlaut(self):
        assert latex_to_unicode('{\\"o}') == "ö"

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


class TestParseName:
    def test_first_last(self):
        assert parse_name("David Gale") == Name(family="Gale", given="David")

    def test_last_first(self):
        assert parse_name("Gale, David") == Name(family="Gale", given="David")

    def test_particle(self):
        n = parse_name("Johannes Diderik van der Waals")
        assert n.family == "van der Waals"
        assert n.given == "Johannes Diderik"

    def test_particle_comma_form(self):
        n = parse_name("van der Waals, Johannes Diderik")
        assert n.family == "van der Waals"

    def test_capitalized_particle(self):
        assert parse_name("Ludwig Van Beethoven").family == "Van Beethoven"

    def test_suffix_comma_form(self):
        n = parse_name("King, Jr., Martin Luther")
        assert n.family == "King"
        assert "Martin Luther" in n.given
        assert "Jr." in n.given

    def test_single_name(self):
        assert parse_name("Aristotle") == Name(family="Aristotle")

    def test_str(self):
        assert str(Name(family="Gale", given="David")) == "Gale, David"
        assert str(Name(literal="ACME Corp")) == "ACME Corp"


class TestSplitAuthors:
    def test_and_split(self):
        authors = split_authors("David Gale and Lloyd S. Shapley")
        assert authors == [
            Name(family="Gale", given="David"),
            Name(family="Shapley", given="Lloyd S."),
        ]

    def test_others_filtered(self):
        authors = split_authors("Howden-Chapman, Philippa and others")
        assert len(authors) == 1
        assert authors[0].family == "Howden-Chapman"

    def test_corporate_literal(self):
        authors = split_authors("{World Health Organization}")
        assert authors == [Name(literal="World Health Organization")]

    def test_and_inside_braces_not_split(self):
        authors = split_authors("{Food and Agriculture Organization} and Smith, John")
        assert authors == [
            Name(literal="Food and Agriculture Organization"),
            Name(family="Smith", given="John"),
        ]

    def test_latex_accents(self):
        authors = split_authors("Farr\\'{e}, L\\'{i}dia")
        assert authors[0].family == "Farré"


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
        assert r.type == "article-journal"

    def test_csl_types(self):
        text = """
@article{a, title={T1}, author={A}, year={2020}}
@book{b, title={T2}, author={B}, year={2020}}
@inproceedings{c, title={T3}, author={C}, year={2020}}
@incollection{d, title={T4}, author={D}, year={2020}}
@phdthesis{e, title={T5}, author={E}, year={2020}}
"""
        types = [r.type for r in parse_bib(text)]
        assert types == [
            "article-journal",
            "book",
            "paper-conference",
            "chapter",
            "thesis",
        ]

    def test_bare_field_values(self):
        text = "@article{bare, title={T}, author={A}, year = 2020, month = jan}"
        r = parse_bib(text)[0]
        assert r.year == 2020
        assert r.extra["month"] == "jan"

    def test_extra_fields_kept(self):
        text = """
@book{knuth, title={TAOCP}, author={Knuth, Donald}, year={1968},
  publisher={Addison-Wesley}, edition={3}, isbn={0-201-89683-4}}
"""
        r = parse_bib(text)[0]
        assert r.extra["publisher"] == "Addison-Wesley"
        assert r.extra["edition"] == "3"
        assert r.extra["isbn"] == "0-201-89683-4"

    def test_booktitle_becomes_journal(self):
        text = (
            "@inproceedings{p, title={T}, author={A},"
            " booktitle={Proc. of X}, year={2020}}"
        )
        r = parse_bib(text)[0]
        assert r.journal == "Proc. of X"
        assert "booktitle" not in r.extra

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


class TestParseBibitem:
    def test_apa_style(self):
        raw = (
            "Priem, J., Piwowar, H., \\& Orr, R. (2022). OpenAlex: A fully-open "
            "index of scholarly works. ArXiv. \\url{https://arxiv.org/abs/2205.01833}"
        )
        r = parse_bibitem("openalex", raw)
        assert r.year == 2022
        assert r.title == "OpenAlex: A fully-open index of scholarly works"
        assert [a.family for a in r.authors] == ["Priem", "Piwowar", "Orr"]
        assert r.authors[0].given == "J."
        assert r.url == "https://arxiv.org/abs/2205.01833"

    def test_apa_venue(self):
        raw = (
            "Van Eck, N., \\& Waltman, L. (2010). Software survey: VOSviewer, "
            "a computer program for bibliometric mapping. "
            "Scientometrics, 84(2), 523-538."
        )
        r = parse_bibitem("vosviewer", raw)
        assert r.authors[0].family == "Van Eck"
        assert r.journal == "Scientometrics"
        assert r.volume == "84"
        assert r.number == "2"
        assert r.pages == "523-538"
        assert r.year == 2010

    def test_newblock_style(self):
        raw = (
            "David Gale and Lloyd S. Shapley.\n\\newblock College admissions and "
            "the stability of marriage.\n\\newblock {\\em The American Mathematical "
            "Monthly}, 69(1):9--15, 1962."
        )
        r = parse_bibitem("gs62", raw)
        assert [a.family for a in r.authors] == ["Gale", "Shapley"]
        assert r.title == "College admissions and the stability of marriage"
        assert r.journal == "The American Mathematical Monthly"
        assert r.volume == "69"
        assert r.pages == "9-15"
        assert r.year == 1962

    def test_initials_not_split_as_sentence(self):
        raw = "J. R. R. Tolkien. The Lord of the Rings. Allen & Unwin, 1954."
        r = parse_bibitem("lotr", raw)
        assert r.title == "The Lord of the Rings"
        assert r.year == 1954

    def test_doi_extracted(self):
        raw = "Someone (2019). A paper. Journal, 1(1), 1-2. https://doi.org/10.1000/xyz123"
        assert parse_bibitem("x", raw).doi == "10.1000/xyz123"


class TestParseTex:
    def test_final_entry_without_end(self):
        text = (
            "\\begin{thebibliography}{9}\n"
            "\\bibitem{a} Author A (2020). First title. Journal, 1(1), 1-2.\n"
            "\\bibitem{b} Author B (2021). Second title. Journal, 2(2), 3-4.\n"
        )
        refs = parse_tex(text)
        assert [r.key for r in refs] == ["a", "b"]
        assert refs[1].year == 2021

    def test_optional_label(self):
        text = (
            "\\bibitem[Gale and Shapley, 1962]{gs62} Gale, D., \\& Shapley, L. "
            "(1962). College admissions. Monthly, 69(1), 9-15.\n"
            "\\end{thebibliography}"
        )
        refs = parse_tex(text)
        assert refs[0].key == "gs62"
        assert refs[0].year == 1962


class TestParseFile:
    def test_unsupported(self, tmp_path: Path):
        p = tmp_path / "test.txt"
        p.write_text("hello")
        try:
            parse_file(p)
            assert False, "Should have raised"
        except ValueError:
            pass
