from hallubib.matching import author_last, first_author_match, title_similarity
from hallubib.sources import SourceError
from hallubib.types import DiffKind, Name, OnlineRecord, Reference, Status
from hallubib.verify import categorize, check_reference


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
