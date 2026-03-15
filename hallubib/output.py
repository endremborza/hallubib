"""Output formatting for stdout, markdown, and HTML."""

import tempfile
import webbrowser
from collections import Counter
from pathlib import Path

from . import cache
from .types import CheckResult, Status


def format_stdout(results: list[CheckResult], filename: str) -> str:
    counts = Counter(r.status for r in results)
    lines = [
        f"hallubib: checked {len(results)} references in {filename}",
        "",
    ]
    for s in Status:
        lines.append(f"  {s.value + ':':<20s} {counts.get(s, 0)}")
    lines.append("")
    lines.append("Run with --output=md or --output=html for detailed breakdown.")
    return "\n".join(lines)


def _ref_label(r: CheckResult) -> str:
    ref = r.reference
    author_str = ref.authors[0].split(",")[0] if ref.authors else "?"
    year_str = str(ref.year) if ref.year else "?"
    return f"`{ref.key}` — {author_str} ({year_str}): {ref.title[:80]}"


def _ref_details(r: CheckResult) -> list[str]:
    lines: list[str] = []
    if r.best_match:
        lines.append(f"  - **Matched**: {r.best_match.source} — {r.best_match.title}")
        if r.best_match.doi:
            lines.append(f"  - **DOI**: {r.best_match.doi}")
    for d in r.diffs:
        lines.append(f"  - **{d.field_name}**: `{d.local_value}` → `{d.online_value}`")
    for note in r.notes:
        lines.append(f"  - {note}")
    return lines


def format_markdown(results: list[CheckResult], filename: str) -> str:
    grouped: dict[Status, list[CheckResult]] = {s: [] for s in Status}
    for r in results:
        grouped[r.status].append(r)

    lines = [f"# hallubib report: {filename}", ""]
    counts = Counter(r.status for r in results)
    lines.append(f"**{len(results)} references checked**\n")
    for s in Status:
        lines.append(f"- {s.value}: {counts.get(s, 0)}")
    lines.append("")

    for status in Status:
        group = grouped[status]
        if not group:
            continue
        lines.append(f"## {status.value} ({len(group)})")
        lines.append("")
        for r in group:
            lines.append(f"### {_ref_label(r)}")
            details = _ref_details(r)
            if details:
                lines.extend(details)
            lines.append("")

    return "\n".join(lines)


_HTML_STYLE = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
       max-width: 900px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #1a1a1a; }
h1 { border-bottom: 2px solid #e1e4e8; padding-bottom: 0.5rem; }
h2 { margin-top: 2rem; }
.summary { background: #f6f8fa; padding: 1rem; border-radius: 6px; margin: 1rem 0; }
.summary span { display: inline-block; margin-right: 1.5rem; }
.ref-card { border: 1px solid #e1e4e8; border-radius: 6px; padding: 1rem; margin: 0.75rem 0; }
.ref-card h3 { margin: 0 0 0.5rem 0; font-size: 0.95rem; }
.ref-card .detail { margin: 0.25rem 0; font-size: 0.9rem; color: #444; }
.ref-card code { background: #f0f0f0; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.85rem; }
.Verified { border-left: 4px solid #28a745; }
.Auto-correctable { border-left: 4px solid #f9a825; }
.Needs-attention { border-left: 4px solid #e65100; }
.Unknown { border-left: 4px solid #d32f2f; }
.badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 3px; font-size: 0.8rem;
         font-weight: 600; color: white; margin-left: 0.5rem; }
.badge-Verified { background: #28a745; }
.badge-Auto-correctable { background: #f9a825; color: #333; }
.badge-Needs-attention { background: #e65100; }
.badge-Unknown { background: #d32f2f; }
"""


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_html(results: list[CheckResult], filename: str) -> str:
    counts = Counter(r.status for r in results)
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>hallubib: {_html_escape(filename)}</title>",
        f"<style>{_HTML_STYLE}</style></head><body>",
        f"<h1>hallubib report: {_html_escape(filename)}</h1>",
        '<div class="summary">',
        f"<strong>{len(results)} references checked</strong><br>",
    ]
    for s in Status:
        css = s.value.replace(" ", "-")
        parts.append(
            f'<span><span class="badge badge-{css}">{s.value}</span> {counts.get(s, 0)}</span>'
        )
    parts.append("</div>")

    grouped: dict[Status, list[CheckResult]] = {s: [] for s in Status}
    for r in results:
        grouped[r.status].append(r)

    for status in Status:
        group = grouped[status]
        if not group:
            continue
        css = status.value.replace(" ", "-")
        parts.append(f"<h2>{status.value} ({len(group)})</h2>")
        for r in group:
            ref = r.reference
            author_str = _html_escape(ref.authors[0].split(",")[0]) if ref.authors else "?"
            year_str = str(ref.year) if ref.year else "?"
            title_str = _html_escape(ref.title[:100])
            parts.append(f'<div class="ref-card {css}">')
            parts.append(
                f"<h3><code>{_html_escape(ref.key)}</code> — {author_str} ({year_str}): {title_str}</h3>"
            )
            if r.best_match:
                src = _html_escape(r.best_match.source)
                mt = _html_escape(r.best_match.title)
                parts.append(f'<p class="detail"><strong>Matched:</strong> {src} — {mt}</p>')
                if r.best_match.doi:
                    doi = _html_escape(r.best_match.doi)
                    parts.append(f'<p class="detail"><strong>DOI:</strong> {doi}</p>')
            for d in r.diffs:
                fn = _html_escape(d.field_name)
                lv = _html_escape(str(d.local_value)) if d.local_value else "—"
                ov = _html_escape(str(d.online_value)) if d.online_value else "—"
                parts.append(
                    f'<p class="detail"><strong>{fn}:</strong> '
                    f"<code>{lv}</code> → <code>{ov}</code></p>"
                )
            for note in r.notes:
                parts.append(f'<p class="detail">{_html_escape(note)}</p>')
            parts.append("</div>")

    parts.append("</body></html>")
    return "\n".join(parts)


def write_html_and_open(results: list[CheckResult], filename: str) -> Path:
    html = format_html(results, filename)
    cache_dir = cache.cache_path()
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        out = cache_dir / "report.html"
        out.write_text(html, encoding="utf-8")
    except OSError:
        fd, tmp = tempfile.mkstemp(suffix=".html", prefix="hallubib_")
        out = Path(tmp)
        with open(fd, "w", encoding="utf-8") as f:
            f.write(html)
    webbrowser.open(out.as_uri())
    return out
