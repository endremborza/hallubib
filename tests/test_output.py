from hallubib.output import format_html, format_markdown, format_stdout
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
