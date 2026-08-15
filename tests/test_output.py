import pytest

from hallubib import cache
from hallubib.output import (
    format_html,
    format_markdown,
    format_stdout,
    write_html_and_open,
)
from hallubib.types import (
    CheckResult,
    DiffKind,
    FieldDiff,
    Name,
    OnlineRecord,
    Reference,
    Status,
)


def _sample_results() -> list[CheckResult]:
    ref_ok = Reference(
        key="gs62",
        title="College Admissions",
        authors=[Name(family="Gale", given="David")],
        type="article-journal",
        year=1962,
    )
    ref_fix = Reference(
        key="bad01",
        title="Some Paper",
        authors=[Name(family="Smith", given="John")],
        type="article-journal",
        year=2001,
        volume="10",
    )
    ref_unk = Reference(
        key="unk99",
        title="Completely Unknown",
        authors=[Name(family="Nobody", given="X")],
        type="article-journal",
        year=1999,
    )
    return [
        CheckResult(reference=ref_ok, status=Status.VERIFIED),
        CheckResult(
            reference=ref_fix,
            status=Status.AUTO_CORRECTABLE,
            best_match=OnlineRecord(
                source="openalex",
                title="Some Paper",
                authors=[Name(family="Smith", given="John")],
                year=2001,
                volume="11",
            ),
            diffs=[FieldDiff("volume", "10", "11", DiffKind.CORRECTION)],
            suggestions={"volume": "11"},
        ),
        CheckResult(
            reference=ref_unk,
            status=Status.UNKNOWN,
            notes=["No matching records found online"],
        ),
    ]


class TestStdout:
    def test_contains_counts(self):
        out = format_stdout(_sample_results(), "test.bib")
        assert "Verified:" in out
        assert "3 references" in out

    def test_suggests_detailed(self):
        out = format_stdout(_sample_results(), "test.bib")
        assert "--output=md" in out


class TestMarkdown:
    def test_has_sections(self):
        md = format_markdown(_sample_results(), "test.bib")
        assert "## Verified" in md
        assert "## Auto-correctable" in md
        assert "## Unknown" in md

    def test_has_diffs(self):
        md = format_markdown(_sample_results(), "test.bib")
        assert "`10`" in md
        assert "`11`" in md

    def test_shows_family_name(self):
        md = format_markdown(_sample_results(), "test.bib")
        assert "Gale (1962)" in md

    def test_header(self):
        md = format_markdown(_sample_results(), "test.bib")
        assert "# hallubib report: test.bib" in md


class TestHtml:
    def test_valid_html(self):
        html = format_html(_sample_results(), "test.bib")
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_has_badges(self):
        html = format_html(_sample_results(), "test.bib")
        assert "badge-Verified" in html
        assert "badge-Unknown" in html

    def test_escapes_html(self):
        ref = Reference(
            key="xss",
            title="<script>alert(1)</script>",
            authors=[Name(family="A", given="B")],
            type="article-journal",
            year=2020,
        )
        results = [CheckResult(reference=ref, status=Status.UNKNOWN)]
        html = format_html(results, "test.bib")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


def _detailed_result(**overrides) -> CheckResult:
    ref = Reference(
        key="det01",
        title="A Detailed Paper",
        authors=[Name(family="Local", given="Ann")],
        type="article-journal",
        year=2020,
    )
    defaults = {
        "reference": ref,
        "status": Status.AUTO_CORRECTABLE,
        "best_match": OnlineRecord(
            source="crossref",
            title="A Detailed Paper",
            authors=[Name(family="Online", given="Bob")],
            year=2019,
            doi="10.1234/detailed",
        ),
    }
    defaults.update(overrides)
    return CheckResult(**defaults)


class TestDiffRendering:
    """The correction/supplement branches shared by markdown and HTML."""

    def test_doi_of_best_match_shown(self):
        results = [_detailed_result()]
        assert "10.1234/detailed" in format_markdown(results, "t.bib")
        assert "10.1234/detailed" in format_html(results, "t.bib")

    def test_year_off_by_one_annotated(self):
        results = [
            _detailed_result(
                diffs=[FieldDiff("year", "2020", "2019", DiffKind.CORRECTION)]
            )
        ]
        assert "online-first vs. print" in format_markdown(results, "t.bib")
        assert "online-first vs. print" in format_html(results, "t.bib")

    def test_year_far_apart_not_annotated(self):
        results = [
            _detailed_result(
                diffs=[FieldDiff("year", "2020", "1999", DiffKind.CORRECTION)]
            )
        ]
        assert "online-first" not in format_markdown(results, "t.bib")
        assert "online-first" not in format_html(results, "t.bib")

    def test_non_numeric_year_does_not_raise(self):
        results = [
            _detailed_result(
                diffs=[FieldDiff("year", "in press", "2019", DiffKind.CORRECTION)]
            )
        ]
        assert "in press" in format_markdown(results, "t.bib")
        assert "in press" in format_html(results, "t.bib")

    def test_supplements_marked_missing(self):
        results = [
            _detailed_result(
                diffs=[FieldDiff("doi", None, "10.1234/new", DiffKind.SUPPLEMENT)]
            )
        ]
        md = format_markdown(results, "t.bib")
        html = format_html(results, "t.bib")
        assert "*(missing)*" in md
        assert "10.1234/new" in md
        assert "<em>(missing)</em>" in html
        assert "10.1234/new" in html

    def test_empty_diff_values_render_as_dash(self):
        results = [
            _detailed_result(
                diffs=[
                    FieldDiff("volume", None, None, DiffKind.CORRECTION),
                    FieldDiff("pages", None, None, DiffKind.SUPPLEMENT),
                ]
            )
        ]
        assert "—" in format_html(results, "t.bib")


class TestAuthorMismatchDetail:
    def test_html_expands_both_author_lists(self):
        results = [
            _detailed_result(
                status=Status.NEEDS_ATTENTION, notes=["First author mismatch"]
            )
        ]
        html = format_html(results, "t.bib")
        assert "Local: Local, Ann" in html
        assert "Online: Online, Bob" in html

    def test_html_handles_empty_author_lists(self):
        ref = Reference(key="noauth", title="No Authors", authors=[], year=2020)
        results = [
            CheckResult(
                reference=ref,
                status=Status.NEEDS_ATTENTION,
                best_match=OnlineRecord(
                    source="crossref", title="No Authors", authors=[]
                ),
                notes=["First author mismatch"],
            )
        ]
        html = format_html(results, "t.bib")
        assert html.count("<em>none</em>") == 2
        assert "?" in html

    def test_note_without_best_match_renders_plainly(self):
        ref = Reference(key="plain", title="Plain", authors=[], year=2020)
        results = [
            CheckResult(
                reference=ref,
                status=Status.NEEDS_ATTENTION,
                notes=["First author mismatch"],
            )
        ]
        html = format_html(results, "t.bib")
        assert "Local:" not in html
        assert '<p class="detail">First author mismatch</p>' in html


class TestUrlReferenceCounts:
    def test_shown_only_when_present(self):
        ref = Reference(
            key="site", title="A Website", authors=[], url="https://example.org"
        )
        with_url = [CheckResult(reference=ref, status=Status.URL_REFERENCE)]
        assert "URL reference:" in format_stdout(with_url, "t.bib")
        assert "- URL reference: 1" in format_markdown(with_url, "t.bib")
        assert "badge-URL-reference" in format_html(with_url, "t.bib")
        assert "URL reference:" not in format_stdout(_sample_results(), "t.bib")


class TestWriteHtmlAndOpen:
    def test_writes_into_cache_dir(self, monkeypatch):
        opened: list[str] = []
        monkeypatch.setattr("hallubib.output.webbrowser.open", opened.append)
        out = write_html_and_open(_sample_results(), "t.bib")
        assert out == cache.cache_path() / "report.html"
        assert "<!DOCTYPE html>" in out.read_text(encoding="utf-8")
        assert opened == [out.as_uri()]

    def test_falls_back_to_tempfile(self, monkeypatch, tmp_path):
        blocked = tmp_path / "not-a-dir"
        blocked.write_text("i am a file", encoding="utf-8")
        monkeypatch.setattr("hallubib.output.cache.cache_path", lambda: blocked)
        monkeypatch.setattr("hallubib.output.webbrowser.open", lambda _: None)
        out = write_html_and_open(_sample_results(), "t.bib")
        try:
            assert out != blocked
            assert out.suffix == ".html"
            assert "<!DOCTYPE html>" in out.read_text(encoding="utf-8")
        finally:
            out.unlink(missing_ok=True)


class TestEmptyResults:
    @pytest.mark.parametrize("fmt", [format_stdout, format_markdown, format_html])
    def test_no_results_still_renders(self, fmt):
        out = fmt([], "empty.bib")
        assert "empty.bib" in out
