from hallubib.types import DiffKind, EntryKind, OnlineRecord, Reference, Status
from hallubib.verify import (
    _author_last,
    _first_author_match,
    _parse_semscholar_paper,
    _title_sim,
    categorize,
)


class TestTitleSim:
    def test_identical(self):
        assert _title_sim("College Admissions", "College Admissions") == 1.0

    def test_case_insensitive(self):
        assert _title_sim("College Admissions", "college admissions") == 1.0

    def test_partial(self):
        sim = _title_sim(
            "College Admissions and the Stability of Marriage",
            "College Admissions and Stability of Marriage"
        )
        assert sim > 0.9

    def test_unrelated(self):
        assert _title_sim("Quantum Computing", "Housing Prices") < 0.3


class TestAuthorMatching:
    def test_last_name_extraction(self):
        assert _author_last("Gale, David") == "gale"
        assert _author_last("David Gale") == "gale"

    def test_first_author_match(self):
        assert _first_author_match(["Gale, David"], ["Gale, D."])
        assert not _first_author_match(["Gale, David"], ["Shapley, Lloyd"])

    def test_empty_lists(self):
        assert _first_author_match([], [])
        assert not _first_author_match(["Gale, David"], [])


def _make_ref(**kwargs) -> Reference:
    defaults = {
        "key": "test", "entry_kind": EntryKind.ARTICLE,
        "title": "Test Title", "authors": ["Last, First"], "year": 2020,
    }
    defaults.update(kwargs)
    return Reference(**defaults)


def _make_online(**kwargs) -> OnlineRecord:
    defaults = {
        "source": "openalex", "title": "Test Title",
        "authors": ["Last, First"], "year": 2020,
    }
    defaults.update(kwargs)
    return OnlineRecord(**defaults)


class TestCategorize:
    def test_verified_exact(self):
        ref = _make_ref(title="College Admissions and the Stability of Marriage")
        rec = _make_online(title="College Admissions and the Stability of Marriage")
        result = categorize(ref, [rec])
        assert result.status == Status.VERIFIED

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

    def test_picks_best_match(self):
        ref = _make_ref(title="Pairwise kidney exchange", authors=["Roth, Alvin E"])
        good = _make_online(title="Pairwise kidney exchange", authors=["Roth, Alvin E"])
        bad = _make_online(title="Some other paper", authors=["Smith, John"])
        result = categorize(ref, [bad, good])
        assert result.status == Status.VERIFIED
        assert result.best_match is not None
        assert result.best_match.title == "Pairwise kidney exchange"

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


class TestSemScholarParser:
    def test_parse_full(self):
        paper = {
            "title": "The Design of Mechanisms for Resource Allocation",
            "authors": [{"name": "Leonid Hurwicz"}],
            "year": 1973,
            "journal": {"name": "American Economic Review", "volume": "63", "pages": "1-30"},
            "externalIds": {"DOI": "10.1234/test"},
        }
        rec = _parse_semscholar_paper(paper)
        assert rec is not None
        assert rec.source == "semanticscholar"
        assert rec.title == "The Design of Mechanisms for Resource Allocation"
        assert rec.authors == ["Hurwicz, Leonid"]
        assert rec.year == 1973
        assert rec.journal == "American Economic Review"
        assert rec.volume == "63"
        assert rec.pages == "1-30"
        assert rec.doi == "10.1234/test"

    def test_parse_no_title(self):
        assert _parse_semscholar_paper({}) is None
        assert _parse_semscholar_paper({"title": None}) is None

    def test_parse_minimal(self):
        rec = _parse_semscholar_paper({"title": "Some Paper"})
        assert rec is not None
        assert rec.authors == []
        assert rec.doi is None
        assert rec.journal is None


