import pytest

from hallubib.matching import author_last, first_author_match, title_similarity
from hallubib.sources import SourceError
from hallubib.types import DiffKind, Name, OnlineRecord, Reference, Status
from hallubib.verify import (
    categorize,
    check_reference,
    check_references,
    check_references_iter,
)


class TestTitleSim:
    def test_identical(self):
        assert title_similarity("College Admissions", "College Admissions") == 1.0

    def test_case_insensitive(self):
        assert title_similarity("College Admissions", "college admissions") == 1.0

    def test_partial(self):
        sim = title_similarity(
            "College Admissions and the Stability of Marriage",
            "College Admissions and Stability of Marriage",
        )
        assert sim > 0.9

    def test_unrelated(self):
        assert title_similarity("Quantum Computing", "Housing Prices") < 0.3


class TestAuthorMatching:
    def test_last_name_extraction(self):
        assert author_last(Name(family="Gale", given="David")) == "gale"
        assert author_last(Name(literal="Gale Institute")) == "institute"

    def test_first_author_match(self):
        gale = [Name(family="Gale", given="David")]
        assert first_author_match(gale, [Name(family="Gale", given="D.")])
        assert not first_author_match(gale, [Name(family="Shapley", given="Lloyd")])

    def test_empty_lists(self):
        assert first_author_match([], [])
        assert not first_author_match([Name(family="Gale")], [])


def _make_ref(**kwargs) -> Reference:
    defaults = {
        "key": "test",
        "title": "Test Title",
        "authors": [Name(family="Last", given="First")],
        "type": "article-journal",
        "year": 2020,
    }
    defaults.update(kwargs)
    return Reference(**defaults)


def _make_online(**kwargs) -> OnlineRecord:
    defaults = {
        "source": "openalex",
        "title": "Test Title",
        "authors": [Name(family="Last", given="First")],
        "year": 2020,
    }
    defaults.update(kwargs)
    return OnlineRecord(**defaults)


class TestCategorize:
    def test_verified_exact(self):
        ref = _make_ref(title="College Admissions and the Stability of Marriage")
        rec = _make_online(title="College Admissions and the Stability of Marriage")
        result = categorize(ref, [rec])
        assert result.status == Status.VERIFIED
        assert result.evidence is not None
        assert result.evidence.title_sim == 1.0
        assert result.score > 0.9

    def test_auto_correctable_volume_diff(self):
        ref = _make_ref(
            title="College Admissions and the Stability of Marriage",
            volume="68",
        )
        rec = _make_online(
            title="College Admissions and the Stability of Marriage",
            volume="69",
        )
        result = categorize(ref, [rec])
        assert result.status == Status.AUTO_CORRECTABLE
        assert any(d.field_name == "volume" for d in result.diffs)

    def test_needs_attention_low_title_sim(self):
        ref = _make_ref(title="College Admissions and Stability")
        rec = _make_online(title="Marriage Stability Problem Revisited")
        result = categorize(ref, [rec])
        assert result.status in (Status.NEEDS_ATTENTION, Status.UNKNOWN)

    def test_unknown_no_candidates(self):
        ref = _make_ref(title="Nonexistent Paper Title")
        result = categorize(ref, [])
        assert result.status == Status.UNKNOWN

    def test_picks_best_match_keeps_alternatives(self):
        ref = _make_ref(
            title="Pairwise kidney exchange",
            authors=[Name(family="Roth", given="Alvin E")],
        )
        good = _make_online(
            title="Pairwise kidney exchange",
            authors=[Name(family="Roth", given="Alvin E")],
        )
        bad = _make_online(
            title="Some other paper", authors=[Name(family="Smith", given="John")]
        )
        result = categorize(ref, [bad, good])
        assert result.status == Status.VERIFIED
        assert result.best_match is not None
        assert result.best_match.title == "Pairwise kidney exchange"
        assert result.alternatives == [bad]

    def test_year_tolerance(self):
        ref = _make_ref(title="Test Paper", year=2020)
        rec = _make_online(title="Test Paper", year=2021)
        result = categorize(ref, [rec])
        assert result.status in (Status.VERIFIED, Status.AUTO_CORRECTABLE)

    def test_verified_with_only_doi_supplement(self):
        ref = _make_ref(title="Test Paper")
        rec = _make_online(title="Test Paper", doi="10.1234/test")
        result = categorize(ref, [rec])
        assert result.status == Status.VERIFIED
        supplements = [d for d in result.diffs if d.kind == DiffKind.SUPPLEMENT]
        assert any(d.field_name == "doi" for d in supplements)

    def test_diff_kind_correction(self):
        ref = _make_ref(title="Test Paper", volume="10")
        rec = _make_online(title="Test Paper", volume="11")
        result = categorize(ref, [rec])
        corrections = [d for d in result.diffs if d.kind == DiffKind.CORRECTION]
        assert any(d.field_name == "volume" for d in corrections)

    def test_online_none_not_flagged(self):
        ref = _make_ref(title="Test Paper", journal="J. Test", volume="5")
        rec = _make_online(title="Test Paper")
        result = categorize(ref, [rec])
        assert not any(d.field_name == "journal" for d in result.diffs)
        assert not any(d.field_name == "volume" for d in result.diffs)

    def test_year_discrepancy_note(self):
        ref = _make_ref(title="Test Paper", year=2020)
        rec = _make_online(title="Test Paper", year=2019)
        result = categorize(ref, [rec])
        assert any("online-first" in n for n in result.notes)


class TestCheckReferenceAttempts:
    def test_network_failure_recorded(self, monkeypatch):
        def fail(*args, **kwargs):
            raise SourceError("openalex", "connection refused")

        monkeypatch.setattr("hallubib.verify.search_openalex_title", fail)
        monkeypatch.setattr("hallubib.verify.search_arxiv", fail)
        monkeypatch.setattr("hallubib.verify.search_crossref", fail)
        monkeypatch.setattr("hallubib.verify.search_semscholar", fail)
        ref = _make_ref(doi=None)
        result = check_reference(ref)
        assert result.status == Status.UNKNOWN
        assert result.attempts
        assert all(not a.ok for a in result.attempts)
        assert any("lookup failed" in n for n in result.notes)

    def test_not_found_is_distinct_from_failure(self, monkeypatch):
        monkeypatch.setattr("hallubib.verify.search_openalex_title", lambda *a, **k: [])
        monkeypatch.setattr("hallubib.verify.search_arxiv", lambda *a, **k: [])
        monkeypatch.setattr("hallubib.verify.search_crossref", lambda *a, **k: [])
        monkeypatch.setattr("hallubib.verify.search_semscholar", lambda *a, **k: [])
        ref = _make_ref(doi=None, year=None)
        result = check_reference(ref)
        assert result.status == Status.UNKNOWN
        assert all(a.ok and a.hits == 0 for a in result.attempts)
        assert not any("lookup failed" in n for n in result.notes)

    def test_doi_fallthrough_reaches_title_search(self, monkeypatch):
        online = _make_online(title="Completely Different Paper")
        good = _make_online(title="Test Title")
        monkeypatch.setattr("hallubib.verify.validate_doi", lambda d: True)
        monkeypatch.setattr("hallubib.verify.search_openalex_doi", lambda d: online)
        monkeypatch.setattr(
            "hallubib.verify.search_openalex_title", lambda *a, **k: [good]
        )
        monkeypatch.setattr("hallubib.verify.search_arxiv", lambda *a, **k: [])
        ref = _make_ref(doi="10.1/x")
        result = check_reference(ref)
        assert result.status == Status.VERIFIED
        assert result.best_match is good


class TestDiffSuppression:
    """Formatting-only differences must not be reported as corrections."""

    @pytest.mark.parametrize("local_pages", ["9--15", "9–15", "9 - 15", "9—15"])
    def test_page_dash_variants_not_flagged(self, local_pages: str):
        ref = _make_ref(title="Test Paper", pages=local_pages)
        rec = _make_online(title="Test Paper", pages="9-15")
        result = categorize(ref, [rec])
        assert not any(d.field_name == "pages" for d in result.diffs)
        assert result.status == Status.VERIFIED

    def test_genuinely_different_pages_flagged(self):
        ref = _make_ref(title="Test Paper", pages="9--15")
        rec = _make_online(title="Test Paper", pages="19-25")
        result = categorize(ref, [rec])
        assert any(d.field_name == "pages" for d in result.diffs)
        assert result.status == Status.AUTO_CORRECTABLE

    def test_title_case_and_punctuation_not_flagged(self):
        ref = _make_ref(title="College Admissions and the Stability of Marriage")
        rec = _make_online(title="College admissions and the stability of marriage!")
        result = categorize(ref, [rec])
        assert not any(d.field_name == "title" for d in result.diffs)
        assert result.status == Status.VERIFIED

    def test_genuinely_different_title_flagged(self):
        ref = _make_ref(title="College Admissions and the Stability of Marriage")
        rec = _make_online(title="College Admissions and the Stability of Markets")
        result = categorize(ref, [rec])
        assert any(d.field_name == "title" for d in result.diffs)

    def test_journal_abbreviation_not_flagged(self):
        ref = _make_ref(title="Test Paper", journal="J. Econ. Theory")
        rec = _make_online(title="Test Paper", journal="Journal of Economic Theory")
        result = categorize(ref, [rec])
        assert not any(d.field_name == "journal" for d in result.diffs)
        assert result.status == Status.VERIFIED

    def test_genuinely_different_journal_flagged(self):
        ref = _make_ref(title="Test Paper", journal="Econometrica")
        rec = _make_online(title="Test Paper", journal="Journal of Economic Theory")
        result = categorize(ref, [rec])
        assert any(d.field_name == "journal" for d in result.diffs)
        assert result.status == Status.NEEDS_ATTENTION


class TestTieBreaking:
    """Sources return several manifestations of the same work - a preprint, a
    tech report, the version of record - which all score alike. Which one wins
    decides what hallubib tells the user to change, so it cannot come down to
    where the title happens to sort."""

    def test_doi_confirmed_candidate_wins_a_tie(self):
        ref = _make_ref(
            title="College Admissions and the Stability of Marriage",
            doi="10.2307/2312726",
        )
        # sorts before the mixed-case title: 'O' < 'o'
        tech_report = _make_online(
            title="COLLEGE ADMISSIONS AND THE STABILITY OF MARRIAGE",
            doi="10.21236/ad0251958",
        )
        of_record = _make_online(
            title="College Admissions and the Stability of Marriage",
            doi="10.2307/2312726",
        )
        result = categorize(ref, [tech_report, of_record])
        assert result.best_match is of_record

    def test_a_valid_doi_is_never_corrected_away(self):
        ref = _make_ref(title="A Paper", doi="10.1234/right")
        other = _make_online(title="A PAPER", doi="10.9999/other")
        mine = _make_online(title="A Paper", doi="10.1234/right")
        result = categorize(ref, [other, mine])
        assert "doi" not in result.suggestions

    def test_doi_match_is_case_insensitive(self):
        ref = _make_ref(title="A Paper", doi="10.1234/Right")
        other = _make_online(title="A PAPER", doi="10.9999/other")
        mine = _make_online(title="A Paper", doi="10.1234/right")
        assert categorize(ref, [other, mine]).best_match is mine

    def test_richer_record_wins_when_no_doi_decides(self):
        ref = _make_ref(title="A Paper")
        sparse = _make_online(title="A PAPER")
        rich = _make_online(title="A Paper", journal="Nature", volume="1", pages="1-9")
        assert categorize(ref, [sparse, rich]).best_match is rich

    def test_ordering_is_stable_for_indistinguishable_candidates(self):
        ref = _make_ref(title="A Paper")
        first = _make_online(title="A Paper", journal="Nature")
        second = _make_online(title="A Paper", journal="Nature")
        assert categorize(ref, [first, second]).best_match is first

    def test_score_still_dominates_the_tie_breakers(self):
        ref = _make_ref(title="A Paper", doi="10.1234/right")
        wrong_work = _make_online(title="A Paper", doi="10.1234/right", year=1900)
        right_work = _make_online(title="A Paper", year=2020)
        assert categorize(ref, [wrong_work, right_work]).best_match is right_work


class TestEmptyOnlineValues:
    """A source that answers with an empty string is telling us it has no value,
    not offering one."""

    def test_empty_string_is_not_a_supplement(self):
        ref = _make_ref(title="A Paper")
        rec = _make_online(title="A Paper", volume="")
        result = categorize(ref, [rec])
        assert not any(d.field_name == "volume" for d in result.diffs)
        assert result.status == Status.VERIFIED

    def test_whitespace_only_is_not_a_supplement(self):
        ref = _make_ref(title="A Paper")
        rec = _make_online(title="A Paper", pages="   ")
        result = categorize(ref, [rec])
        assert not any(d.field_name == "pages" for d in result.diffs)
        assert result.status == Status.VERIFIED

    def test_empty_string_is_not_a_correction_either(self):
        ref = _make_ref(title="A Paper", volume="69")
        rec = _make_online(title="A Paper", volume="")
        result = categorize(ref, [rec])
        assert not any(d.field_name == "volume" for d in result.diffs)

    def test_empty_local_value_still_takes_a_supplement(self):
        ref = _make_ref(title="A Paper", volume="")
        rec = _make_online(title="A Paper", volume="69")
        result = categorize(ref, [rec])
        volume = next(d for d in result.diffs if d.field_name == "volume")
        assert volume.kind == DiffKind.SUPPLEMENT
        assert result.suggestions["volume"] == "69"


class TestUnresolvableDoi:
    """A fabricated DOI is the loudest hallucination signal there is; matching
    the title anyway must not let the entry through as Verified."""

    def test_verified_is_downgraded(self, sources: "_Sources"):
        sources.set(
            validate_doi=lambda doi: False,
            search_openalex_title=lambda *a, **k: [_make_online(title="Test Title")],
        )
        result = check_reference(_make_ref(doi="10.9999/nope"))
        assert result.status == Status.NEEDS_ATTENTION
        assert any("DOI does not resolve" in n for n in result.notes)

    def test_auto_correctable_is_downgraded(self, sources: "_Sources"):
        sources.set(
            validate_doi=lambda doi: False,
            search_openalex_title=lambda *a, **k: [
                _make_online(title="Test Title", volume="9")
            ],
        )
        result = check_reference(_make_ref(doi="10.9999/nope", volume="8"))
        assert result.status == Status.NEEDS_ATTENTION

    def test_unknown_is_left_alone(self, sources: "_Sources"):
        sources.set(validate_doi=lambda doi: False)
        result = check_reference(_make_ref(doi="10.9999/nope"))
        assert result.status == Status.UNKNOWN

    def test_resolving_doi_still_verifies(self, sources: "_Sources"):
        sources.set(
            search_openalex_doi=lambda doi: _make_online(title="Test Title"),
        )
        result = check_reference(_make_ref(doi="10.1234/real"))
        assert result.status == Status.VERIFIED

    def test_reference_without_a_doi_is_unaffected(self, sources: "_Sources"):
        sources.set(
            search_openalex_title=lambda *a, **k: [_make_online(title="Test Title")],
        )
        result = check_reference(_make_ref(doi=None))
        assert result.status == Status.VERIFIED


class TestNeedsAttentionNotes:
    def test_partial_title_match_reports_similarity(self):
        ref = _make_ref(title="Pairwise Kidney Exchange")
        rec = _make_online(title="Pairwise Kidney Exchange Mechanisms")
        result = categorize(ref, [rec])
        assert result.status == Status.NEEDS_ATTENTION
        assert any("Title similarity" in n for n in result.notes)

    def test_first_author_mismatch_noted(self):
        ref = _make_ref(title="Pairwise Kidney Exchange", authors=[Name(family="Roth")])
        rec = _make_online(
            title="Pairwise Kidney Exchange Mechanisms",
            authors=[Name(family="Sonmez")],
        )
        result = categorize(ref, [rec])
        assert result.status == Status.NEEDS_ATTENTION
        assert "First author mismatch" in result.notes

    def test_year_mismatch_noted(self):
        ref = _make_ref(title="Pairwise Kidney Exchange", year=2020)
        rec = _make_online(title="Pairwise Kidney Exchange Mechanisms", year=2005)
        result = categorize(ref, [rec])
        assert result.status == Status.NEEDS_ATTENTION
        assert any("Year mismatch" in n for n in result.notes)

    def test_unrelated_candidate_is_unknown(self):
        ref = _make_ref(title="Pairwise Kidney Exchange")
        rec = _make_online(title="Quantum Chromodynamics on the Lattice")
        result = categorize(ref, [rec])
        assert result.status == Status.UNKNOWN
        assert any("Best candidate" in n for n in result.notes)


class _Sources:
    """Stub every network entry point in verify and record the call order."""

    def __init__(self, monkeypatch):
        self._mp = monkeypatch
        self.calls: list[str] = []
        self.set(
            validate_doi=lambda doi: True,
            search_openalex_doi=lambda doi: None,
            search_openalex_title=lambda *a, **k: [],
            search_arxiv=lambda *a, **k: [],
            search_crossref=lambda *a, **k: [],
            search_semscholar=lambda *a, **k: [],
            validate_url=lambda url, session: True,
        )

    def set(self, **fns) -> None:
        for name, fn in fns.items():
            self._mp.setattr(f"hallubib.verify.{name}", self._record(name, fn))

    def _record(self, name, fn):
        def wrapper(*args, **kwargs):
            self.calls.append(name)
            return fn(*args, **kwargs)

        return wrapper


@pytest.fixture
def sources(monkeypatch) -> _Sources:
    return _Sources(monkeypatch)


class TestUrlOnlyReferences:
    def _url_ref(self, url: str) -> Reference:
        return _make_ref(title="Some Tool", url=url, year=None, authors=[])

    def test_reachable_github_repo(self, sources: _Sources):
        result = check_reference(self._url_ref("https://github.com/user/repo"))
        assert result.status == Status.URL_REFERENCE
        assert any("GitHub repository" in n for n in result.notes)
        assert "URL is reachable" in result.notes
        assert result.attempts[0].source == "url"
        assert result.attempts[0].hits == 1

    def test_unreachable_url_is_unknown(self, sources: _Sources):
        sources.set(validate_url=lambda url, session: False)
        result = check_reference(self._url_ref("https://example.org/gone"))
        assert result.status == Status.UNKNOWN
        assert "URL is not reachable" in result.notes

    def test_plain_website_note(self, sources: _Sources):
        result = check_reference(self._url_ref("https://example.org/tool"))
        assert any(n.startswith("URL: ") for n in result.notes)

    def test_no_bibliographic_source_consulted(self, sources: _Sources):
        check_reference(self._url_ref("https://github.com/user/repo"))
        assert sources.calls == ["validate_url"]


class TestDoiHandling:
    def test_verified_by_doi_short_circuits(self, sources: _Sources):
        rec = _make_online(title="Test Title")
        sources.set(search_openalex_doi=lambda doi: rec)
        result = check_reference(_make_ref(doi="10.1/x"))
        assert result.status == Status.VERIFIED
        assert sources.calls == ["validate_doi", "search_openalex_doi"]

    def test_unresolvable_doi_noted(self, sources: _Sources):
        sources.set(validate_doi=lambda doi: False)
        result = check_reference(_make_ref(doi="10.9999/nope"))
        assert any("DOI does not resolve" in n for n in result.notes)
        assert "search_openalex_doi" not in sources.calls

    def test_doi_lookup_failure_recorded_but_not_fatal(self, sources: _Sources):
        def fail(doi):
            raise SourceError("doi", "timeout")

        sources.set(validate_doi=fail)
        result = check_reference(_make_ref(doi="10.1/x"))
        doi_attempt = next(a for a in result.attempts if a.source == "doi")
        assert not doi_attempt.ok
        assert doi_attempt.error == "timeout"
        assert not any("DOI does not resolve" in n for n in result.notes)


class TestSourceEscalation:
    def test_arxiv_only_when_nothing_found(self, sources: _Sources):
        sources.set(search_openalex_title=lambda *a, **k: [_make_online()])
        check_reference(_make_ref(doi=None))
        assert "search_arxiv" not in sources.calls

    def test_arxiv_always_for_arxiv_urls(self, sources: _Sources):
        sources.set(search_openalex_title=lambda *a, **k: [_make_online()])
        check_reference(_make_ref(doi=None, url="https://arxiv.org/abs/1234.5678"))
        assert "search_arxiv" in sources.calls

    def test_crossref_and_s2_only_when_unresolved(self, sources: _Sources):
        sources.set(search_openalex_title=lambda *a, **k: [_make_online()])
        check_reference(_make_ref(doi=None))
        assert "search_crossref" not in sources.calls
        assert "search_semscholar" not in sources.calls

    def test_crossref_rescues_an_unknown(self, sources: _Sources):
        good = _make_online(source="crossref", title="Test Title")
        sources.set(search_crossref=lambda *a, **k: [good])
        result = check_reference(_make_ref(doi=None))
        assert result.status == Status.VERIFIED
        assert result.best_match is good

    def test_widened_year_search_is_last_resort(self, sources: _Sources):
        check_reference(_make_ref(doi=None, year=2020))
        assert sources.calls.count("search_openalex_title") == 2

    def test_no_widened_search_without_year(self, sources: _Sources):
        check_reference(_make_ref(doi=None, year=None))
        assert sources.calls.count("search_openalex_title") == 1

    def test_widened_search_result_used(self, sources: _Sources):
        good = _make_online(title="Test Title")
        calls = {"n": 0}

        def title_search(*args, **kwargs):
            calls["n"] += 1
            return [good] if calls["n"] > 1 else []

        sources.set(search_openalex_title=title_search)
        result = check_reference(_make_ref(doi=None, year=2020))
        assert result.status == Status.VERIFIED


class TestConcurrentChecks:
    def test_results_keep_input_order(self, sources: _Sources):
        def by_title(title, *args, **kwargs):
            return [_make_online(title=title)]

        sources.set(search_openalex_title=by_title)
        refs = [_make_ref(key=f"r{i}", title=f"Paper {i}", doi=None) for i in range(8)]
        results = check_references(refs, max_workers=4)
        assert [r.reference.key for r in results] == [r.key for r in refs]
        assert all(r.status == Status.VERIFIED for r in results)

    def test_iterator_yields_indices(self, sources: _Sources):
        refs = [_make_ref(key=f"r{i}", doi=None) for i in range(4)]
        seen = dict(check_references_iter(refs, max_workers=2))
        assert sorted(seen) == [0, 1, 2, 3]

    def test_worker_exception_becomes_unknown(self, monkeypatch):
        def explode(ref):
            raise RuntimeError("worker blew up")

        monkeypatch.setattr("hallubib.verify.check_reference", explode)
        results = check_references([_make_ref(doi=None)], max_workers=1)
        assert results[0].status == Status.UNKNOWN
        assert any("Error during verification" in n for n in results[0].notes)

    def test_empty_input(self):
        assert check_references([]) == []
