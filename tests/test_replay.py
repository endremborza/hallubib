"""Full pipeline over golden.bib, served from recorded API responses.

Every reference in golden.bib exercises a different route through
`verify.check_reference`; the assertions below pin the route, not the prose of
whatever the sources happen to return. Re-record with
`uv run python -m tests.record_cassettes` when a source's schema moves.
"""

import json

import pytest

from hallubib.output import format_html, format_markdown, format_stdout
from hallubib.parser import parse_file
from hallubib.serialize import results_to_dict
from hallubib.types import CheckResult, DiffKind, Status
from hallubib.verify import check_references

from .conftest import GOLDEN_BIB


@pytest.fixture
def checked(cassette) -> dict[str, CheckResult]:
    refs = parse_file(GOLDEN_BIB)
    return {r.reference.key: r for r in check_references(refs, max_workers=4)}


def _diff(result: CheckResult, field: str):
    return next((d for d in result.diffs if d.field_name == field), None)


def _attempt(result: CheckResult, source: str):
    return next((a for a in result.attempts if a.source == source), None)


class TestCoverageOfTheBib:
    def test_every_reference_produces_a_result(self, cassette):
        refs = parse_file(GOLDEN_BIB)
        results = check_references(refs, max_workers=4)
        assert len(results) == len(refs) == 12
        assert [r.reference.key for r in results] == [r.key for r in refs]

    def test_every_result_records_its_attempts(self, checked):
        for key, result in checked.items():
            assert result.attempts, f"{key} recorded no attempts"

    def test_no_source_lookup_failed(self, checked):
        for key, result in checked.items():
            failed = [a.source for a in result.attempts if not a.ok]
            assert not failed, f"{key} had failed lookups: {failed}"


class TestVerifiedRoutes:
    def test_doi_route(self, checked):
        r = checked["galeshapley62"]
        doi_attempt = _attempt(r, "doi")
        assert doi_attempt is not None and doi_attempt.hits == 1
        assert r.status in (Status.VERIFIED, Status.AUTO_CORRECTABLE)
        assert r.evidence is not None and r.evidence.title_sim > 0.95

    def test_a_resolving_doi_is_matched_to_its_own_record(self, checked):
        """OpenAlex also returns the 1961 tech-report manifestation for this
        title; picking it would have us rewrite a correct DOI."""
        r = checked["galeshapley62"]
        assert r.best_match is not None
        assert r.best_match.doi == "10.2307/2312726"
        assert "doi" not in r.suggestions

    def test_title_route_without_doi(self, checked):
        r = checked["hurwicz73"]
        assert r.status == Status.VERIFIED
        assert _attempt(r, "doi") is None
        assert r.best_match is not None
        assert r.best_match.journal == "The American Economic Review"

    def test_arxiv_route(self, checked):
        r = checked["vaswani17"]
        assert r.status == Status.VERIFIED
        assert _attempt(r, "arxiv") is not None
        assert r.best_match is not None
        assert r.best_match.source == "arxiv"
        assert r.best_match.ids["arxiv"].startswith("1706.03762")

    def test_escalates_to_crossref_and_s2_only_when_needed(self, checked):
        assert _attempt(checked["vaswani17"], "crossref") is None
        assert _attempt(checked["wrongvolume"], "crossref") is not None
        assert _attempt(checked["wrongvolume"], "semanticscholar") is not None


class TestCorrectableRoutes:
    def test_wrong_volume_is_reported(self, checked):
        r = checked["wrongvolume"]
        volume = _diff(r, "volume")
        assert volume is not None
        assert (volume.local_value, volume.online_value) == ("11", "92")
        assert volume.kind == DiffKind.CORRECTION

    def test_missing_doi_offered_as_supplement(self, checked):
        r = checked["wrongvolume"]
        doi = _diff(r, "doi")
        assert doi is not None and doi.kind == DiffKind.SUPPLEMENT
        assert r.suggestions["doi"] == "10.1086/261272"

    def test_version_of_record_beats_the_working_paper(self, checked):
        """Crossref and OpenAlex both carry the NBER working paper (2007, DOI
        10.3386/w13225) alongside the journal article. The fuller record is the
        one worth completing the entry from."""
        r = checked["roth08"]
        assert r.status == Status.AUTO_CORRECTABLE
        assert r.best_match is not None
        assert r.best_match.journal == "International Journal of Game Theory"
        assert r.suggestions["doi"] == "10.1007/s00182-008-0117-6"
        assert r.suggestions["pages"] == "537-569"
        assert not any(d.field_name == "year" for d in r.diffs)

    def test_year_far_off_needs_attention(self, checked):
        r = checked["wrongyear"]
        assert r.status == Status.NEEDS_ATTENTION
        assert r.evidence is not None and not r.evidence.year_ok
        assert any("Year mismatch" in n for n in r.notes)


class TestFailureRoutes:
    def test_unregistered_doi_is_called_out(self, checked):
        r = checked["deaddoi"]
        doi_attempt = _attempt(r, "doi")
        assert doi_attempt is not None and doi_attempt.hits == 0
        assert any("DOI does not resolve" in n for n in r.notes)
        assert r.status == Status.NEEDS_ATTENTION

    def test_empty_field_from_a_source_is_not_offered_as_a_fix(self, checked):
        """Semantic Scholar answers with volume="" for this one."""
        r = checked["deaddoi"]
        assert not r.diffs
        assert not r.suggestions

    def test_invented_reference_stays_unknown(self, checked):
        r = checked["hallucinated"]
        assert r.status == Status.UNKNOWN
        assert r.evidence is not None and r.evidence.title_sim < 0.7

    def test_unknown_triggers_the_widened_year_search(self, checked):
        openalex = [
            a for a in checked["hallucinated"].attempts if a.source == "openalex"
        ]
        assert len(openalex) == 2
        assert openalex[1].query.startswith("title-any-year:")

    def test_book_not_indexed_needs_attention(self, checked):
        r = checked["mascolell95"]
        assert r.status == Status.NEEDS_ATTENTION
        assert "First author mismatch" in r.notes


class TestUrlRoutes:
    def test_github_repository(self, checked):
        r = checked["githubrepo"]
        assert r.status == Status.URL_REFERENCE
        assert any("GitHub repository" in n for n in r.notes)

    def test_plain_website(self, checked):
        r = checked["website"]
        assert r.status == Status.URL_REFERENCE
        assert "URL is reachable" in r.notes

    def test_dead_link(self, checked):
        r = checked["deadlink"]
        assert r.status == Status.UNKNOWN
        assert "URL is not reachable" in r.notes

    def test_url_only_refs_skip_the_bibliographic_sources(self, checked):
        for key in ("githubrepo", "website", "deadlink"):
            assert [a.source for a in checked[key].attempts] == ["url"]


class TestCacheBehaviour:
    def test_second_pass_is_served_from_disk(self, cassette):
        refs = parse_file(GOLDEN_BIB)
        check_references(refs, max_workers=4)
        first_pass = len(cassette.calls)
        assert first_pass > 0

        cassette.calls.clear()
        check_references(refs, max_workers=4)
        assert cassette.calls == []

    def test_every_recorded_interaction_is_reachable(self, cassette):
        check_references(parse_file(GOLDEN_BIB), max_workers=4)
        http_keys = {k for k in cassette.interactions if not k.startswith("URLCHECK ")}
        unused = http_keys - set(cassette.calls)
        assert not unused, f"stale cassette entries: {sorted(unused)}"


class TestOutputOverRealResults:
    def test_stdout(self, checked):
        out = format_stdout(list(checked.values()), "golden.bib")
        assert "checked 12 references" in out
        assert "URL reference:" in out

    def test_markdown_groups_every_status_present(self, checked):
        md = format_markdown(list(checked.values()), "golden.bib")
        present = {r.status for r in checked.values()}
        for status in present:
            assert f"## {status.value}" in md

    def test_html_is_well_formed(self, checked):
        html = format_html(list(checked.values()), "golden.bib")
        assert html.startswith("<!DOCTYPE html>")
        assert html.rstrip().endswith("</body></html>")
        assert html.count('<div class="ref-card') == 12

    def test_json_is_serialisable(self, checked):
        payload = results_to_dict(checked.values())
        text = json.dumps(payload, ensure_ascii=False)
        assert json.loads(text)["hallubib_version"]
        assert len(json.loads(text)["results"]) == 12
