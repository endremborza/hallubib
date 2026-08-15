"""Edge branches that the mainline suites never reach.

Mostly degenerate input and fail-soft guarantees: malformed names, unwritable
caches, missing data files. Each one is a contract - hallubib is supposed to
degrade rather than raise on any of these.
"""

import gzip
import subprocess
import sys
from pathlib import Path

import pytest

from hallubib import abbrevs, cache
from hallubib.bib import entry_to_bib
from hallubib.csl import from_csl, to_csl
from hallubib.matching import author_last, author_overlap
from hallubib.names import latex_to_unicode, parse_name, split_authors
from hallubib.parser import parse_bib, parse_bibitem
from hallubib.serialize import result_to_dict
from hallubib.sources import _http
from hallubib.types import CheckResult, Name, OnlineRecord, Reference, Status


def _ref(**kwargs) -> Reference:
    defaults = {"key": "k", "title": "T", "authors": [], "type": "article-journal"}
    defaults.update(kwargs)
    return Reference(**defaults)


class TestNameEdges:
    def test_empty_string_is_an_empty_name(self):
        assert parse_name("") == Name()
        assert parse_name("   ") == Name()

    def test_family_only_stringifies_bare(self):
        assert str(Name(family="Gale")) == "Gale"
        assert str(Name(family="Gale", given="David")) == "Gale, David"
        assert str(Name(literal="OurResearch")) == "OurResearch"

    def test_suffix_without_comma(self):
        n = parse_name("Alvin E Roth Jr")
        assert n.family == "Roth"
        assert "Jr" in n.given

    def test_others_is_dropped(self):
        assert [n.family for n in split_authors("Gale, David and others")] == ["Gale"]

    def test_part_that_normalizes_to_nothing_is_dropped(self):
        assert [n.family for n in split_authors("Gale, David and ~")] == ["Gale"]

    def test_unbalanced_braces_are_not_literal_names(self):
        names = split_authors("{{a}")
        assert names and not names[0].literal

    def test_brace_wrapped_corporate_name(self):
        assert split_authors("{World Health Organization}") == [
            Name(literal="World Health Organization")
        ]


class TestLatexCommands:
    """A LaTeX control word is a maximal run of letters, so `\\url` is one
    command - not the breve accent `\\u` applied to `r`. Non-accent commands are
    left alone (braces are still stripped, as they are for `\\emph`); only the
    punctuation accents may bind to the next letter without a separator.
    """

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (r"\url{http://x.test}", r"\urlhttp://x.test"),
            (r"\cite{key}", r"\citekey"),
            (r"\ref{fig}", r"\reffig"),
            (r"\dots", r"\dots"),
            (r"\emph{Nature}", r"\emphNature"),
        ],
    )
    def test_letter_commands_are_not_read_as_accents(self, raw, expected):
        assert latex_to_unicode(raw) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (r"S\'onmez", "Sónmez"),
            ('S\\"onmez', "Sönmez"),
            (r"Dr\`eze", "Drèze"),
            (r"C\^ote", "Côte"),
            (r"Mu\~noz", "Muñoz"),
        ],
    )
    def test_punctuation_accents_bind_without_a_separator(self, raw, expected):
        assert latex_to_unicode(raw) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (r"\u{g}", "ğ"),
            (r"\u g", "ğ"),
            (r"\c{c}", "ç"),
            (r"\c c", "ç"),
            (r"\v{s}", "š"),
            (r"\v s", "š"),
        ],
    )
    def test_letter_accents_need_braces_or_a_separator(self, raw, expected):
        assert latex_to_unicode(raw) == expected

    def test_accented_letter_keeps_the_rest_of_its_word(self):
        assert latex_to_unicode(r"\v sonmez") == "šonmez"


class TestMatchingEdges:
    def test_nameless_name_has_no_last_name(self):
        assert author_last(Name()) == ""
        assert author_last(Name(literal="   ")) == ""

    def test_two_empty_author_lists_overlap_fully(self):
        assert author_overlap([], []) == 1.0

    def test_one_empty_list_does_not_overlap(self):
        assert author_overlap([], [Name(family="Gale")]) == 0.0

    def test_unusable_names_do_not_overlap(self):
        assert author_overlap([Name()], [Name(family="Gale")]) == 0.0


class TestCslEdges:
    def test_numeric_month_kept(self):
        assert to_csl(_ref(year=2020, extra={"month": "3"}))["issued"] == {
            "date-parts": [[2020, 3]]
        }

    def test_named_month_mapped(self):
        assert to_csl(_ref(year=2020, extra={"month": "january"}))["issued"] == {
            "date-parts": [[2020, 1]]
        }

    def test_unparseable_month_dropped(self):
        assert to_csl(_ref(year=2020, extra={"month": "brumaire"}))["issued"] == {
            "date-parts": [[2020]]
        }

    @pytest.mark.parametrize("alias", ["school", "institution"])
    def test_publisher_aliases(self, alias):
        assert to_csl(_ref(extra={alias: "MIT"}))["publisher"] == "MIT"

    def test_explicit_publisher_wins_over_alias(self):
        csl = to_csl(_ref(extra={"publisher": "Springer", "school": "MIT"}))
        assert csl["publisher"] == "Springer"

    def test_online_record_carries_bibliographic_detail(self):
        rec = OnlineRecord(
            source="crossref",
            title="A Paper",
            authors=[Name(family="Doe", given="Jane")],
            year=2020,
            journal="Nature",
            volume="580",
            number="7801",
            pages="1-5",
            doi="10.1038/x",
            url="https://doi.org/10.1038/x",
        )
        csl = to_csl(rec)
        assert csl["volume"] == "580"
        assert csl["issue"] == "7801"
        assert csl["page"] == "1-5"
        assert csl["URL"] == "https://doi.org/10.1038/x"
        assert csl["custom"]["source"] == "crossref"

    def test_container_title_as_list(self):
        assert from_csl({"id": "x", "container-title": ["Nature"]}).journal == "Nature"

    def test_empty_container_title_list(self):
        assert from_csl({"id": "x", "container-title": []}).journal is None


class TestBibEdges:
    def test_masters_thesis_detected_from_genre(self):
        entry = entry_to_bib({"id": "t", "type": "thesis", "genre": "Master's thesis"})
        assert entry.startswith("@mastersthesis{")

    def test_doctoral_thesis_stays_phdthesis(self):
        entry = entry_to_bib({"id": "t", "type": "thesis", "genre": "PhD thesis"})
        assert entry.startswith("@phdthesis{")


class TestSerializeSingle:
    def test_one_result_round_trips(self):
        result = CheckResult(reference=_ref(), status=Status.VERIFIED)
        as_dict = result_to_dict(result)
        assert as_dict["status"] == "Verified"
        assert as_dict["reference"]["key"] == "k"


class TestCacheFailsSoft:
    def test_corrupt_entry_reads_as_a_miss(self, tmp_path):
        from hallubib import configure

        configure(cache_dir=tmp_path)
        cache.put("ns", "broken", {"v": 1})
        (tmp_path / "ns" / "broken.json").write_text("{not json", encoding="utf-8")
        assert cache.get("ns", "broken") is None

    def test_unwritable_cache_does_not_raise(self, tmp_path):
        from hallubib import configure

        blocked = tmp_path / "blocked"
        blocked.write_text("i am a file", encoding="utf-8")
        configure(cache_dir=blocked)
        cache.put("ns", "k", {"v": 1})
        assert cache.get("ns", "k") is None

    def test_clear_on_absent_dir_is_a_no_op(self, tmp_path):
        from hallubib import configure

        configure(cache_dir=tmp_path / "never-created")
        cache.clear()


class _Headers:
    """Only `.headers` is read off the response when computing a retry delay."""

    def __init__(self, headers: dict):
        self.headers = headers


class TestRetryDelay:
    def test_numeric_retry_after_honoured(self):
        assert _http._retry_delay(_Headers({"Retry-After": "7"}), 0) == 7.0

    def test_retry_after_beyond_tolerance_means_do_not_retry(self):
        assert _http._retry_delay(_Headers({"Retry-After": "9999"}), 0) is None

    def test_retry_after_at_the_tolerance_is_honoured(self):
        assert _http._retry_delay(_Headers({"Retry-After": "30"}), 0) == 30.0

    def test_http_date_retry_after_falls_back_to_backoff(self):
        header = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
        assert _http._retry_delay(_Headers(header), 2) == 4.0

    def test_absent_retry_after_backs_off_exponentially(self):
        assert _http._retry_delay(_Headers({}), 0) == 1.0
        assert _http._retry_delay(_Headers({}), 2) == 4.0


class TestAbbrevDataFile:
    @pytest.fixture(autouse=True)
    def reset_abbrevs(self, monkeypatch):
        monkeypatch.setattr(abbrevs, "_loaded", False)
        monkeypatch.setattr(abbrevs, "_full_to_abbrev", {})
        monkeypatch.setattr(abbrevs, "_abbrev_to_full", {})

    def test_missing_data_file_degrades_quietly(self, monkeypatch, tmp_path):
        monkeypatch.setattr(abbrevs, "_ABBREV_FILE", tmp_path / "absent.csv.gz")
        assert abbrevs.known_count() == 0
        assert abbrevs.expand("J. Econ. Theory") == "j econ theory"

    def test_malformed_rows_are_skipped(self, monkeypatch, tmp_path):
        path = tmp_path / "abbrevs.csv.gz"
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write("Journal of Economic Theory,J. Econ. Theory\n")
            f.write("only-one-column\n")
            f.write(",J. Empty Full\n")
            f.write("Empty Abbrev,\n")
            f.write("Same,Same\n")
        monkeypatch.setattr(abbrevs, "_ABBREV_FILE", path)
        assert abbrevs.known_count() == 1
        assert abbrevs.expand("J. Econ. Theory") == "journal of economic theory"


class TestModuleEntryPoint:
    def test_python_dash_m_runs_the_cli(self):
        proc = subprocess.run(
            [sys.executable, "-m", "hallubib", "--version"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert proc.returncode == 0
        assert "hallubib" in proc.stdout


class TestBibFieldEdges:
    def test_booktitle_kept_when_journal_also_present(self):
        refs = parse_bib(
            "@inproceedings{k, title={T}, author={A, B}, "
            "journal={J}, booktitle={Proc. of X}, year={2020}}"
        )
        assert refs[0].journal == "J"
        assert refs[0].extra["booktitle"] == "Proc. of X"

    def test_booktitle_becomes_journal_when_alone(self):
        refs = parse_bib(
            "@inproceedings{k, title={T}, author={A, B}, "
            "booktitle={Proc. of X}, year={2020}}"
        )
        assert refs[0].journal == "Proc. of X"

    def test_unparseable_year_is_preserved_verbatim(self):
        refs = parse_bib("@article{k, title={T}, author={A, B}, year={forthcoming}}")
        assert refs[0].year is None
        assert refs[0].extra["year"] == "forthcoming"


class TestFreeTextParsing:
    def test_quoted_title_is_split_off_the_venue(self):
        r = parse_bibitem(
            "q1",
            "Gale, D. and Shapley, L. (1962). ``College Admissions and the "
            "Stability of Marriage''. American Mathematical Monthly, 69, 9-15.",
        )
        assert r.title == "College Admissions and the Stability of Marriage"
        assert r.journal == "American Mathematical Monthly"
        assert r.pages == "9-15"

    def test_single_sentence_entry_keeps_the_whole_text_as_title(self):
        r = parse_bibitem("s1", "An Untitled Note With No Sentence Break")
        assert r.title == "An Untitled Note With No Sentence Break"
        assert r.authors == []

    def test_author_segment_of_only_digits_is_dropped(self):
        r = parse_bibitem("d1", "1962, 1963. A Paper. Some Journal, 1, 2-3.")
        assert all(a.family or a.literal for a in r.authors)

    def test_et_al_and_ellipsis_dropped(self):
        r = parse_bibitem(
            "e1",
            "Roth, A. et al. Pairwise Kidney Exchange. J. Econ. Theory, 125, 1-10.",
        )
        assert [a.family for a in r.authors] == ["Roth"]

    def test_venue_without_a_journal_head(self):
        r = parse_bibitem("v1", "Doe, J. (2020). A Title. Retrieved from somewhere.")
        assert r.journal is None

    def test_entry_with_no_author_block_yields_no_authors(self):
        r = parse_bibitem("x1", ". A Title Without Authors. Some Journal, 1, 2-3.")
        assert r.authors == []
        assert r.title == "A Title Without Authors"
