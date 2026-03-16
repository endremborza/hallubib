# hallubib

[![pypi](https://img.shields.io/pypi/v/hallubib.svg)](https://pypi.org/project/hallubib/)

Check bibliography references for hallucinations. Parses `.bib` and `.tex` files, verifies each reference against online sources (OpenAlex, Semantic Scholar, Crossref, arXiv, DOI resolution), and categorizes them by confidence.

## Installation

```bash
# With uv (recommended)
uv tool install hallubib
# Or with pip
pip install hallubib
```

## Usage

```bash
# Quick summary (default)
hallubib references.bib

# Detailed markdown report
hallubib paper.tex --output=md

# HTML report (opens in browser)
hallubib references.bib --output=html

# Clear the cache
hallubib --clear-cache
```

### Output modes

| Flag | Description |
|------|-------------|
| `--output=stdout` | (default) Summary counts per category |
| `--output=md` | Detailed markdown breakdown to stdout |
| `--output=html` | Styled HTML report, opened in default browser |

## How it works

### 1. Parse

The parser module handles two formats:
- **`.bib` files**: Full BibTeX parsing with LaTeX accent normalization
- **`.tex` files**: Extracts `\bibitem` entries from `thebibliography` environments using heuristic text parsing

### 2. Verify

Each reference is checked against online sources in this order:
1. **DOI validation**: If a DOI is present, verify it resolves via `doi.org`
2. **OpenAlex lookup**: Search by DOI (fast path) or by title (full-text search with ±1 year filter)
3. **arXiv search**: For arXiv-linked papers or as fallback when OpenAlex yields nothing
4. **Crossref + Semantic Scholar fallback**: If not yet verified/auto-correctable, search both for broader coverage (especially older papers without DOIs)
5. **Wider search**: If still unknown, retry OpenAlex without year filter

URL-only references (GitHub repos, websites) are validated for reachability instead of bibliographic matching.

API calls run concurrently (thread pool) for speed.

### 3. Categorize

Each reference is assigned one of five statuses:

| Status | Meaning |
|--------|---------|
| **Unknown** | No plausible match found online |
| **Needs attention** | Partial match — ambiguous, may be wrong edition or different paper |
| **Auto-correctable** | Match found but some fields differ (e.g., volume, year, journal name) |
| **URL reference** | Not a traditional article — URL validated for reachability |
| **Verified** | Match found; all fields consistent or only missing optional info (DOI, issue number) |

Output is ordered most-problematic-first for easy triage.

Matching uses:
- Title similarity (normalized, accent-stripped, fuzzy matching)
- First-author last name matching
- Year tolerance (±1 year for preprint/publication date differences)
- Journal name fuzzy matching with 41K+ abbreviation database

Field differences are classified as:
- **Corrections**: local value conflicts with online value
- **Supplements**: local value missing, online has it (shown as *(missing)*)

### 4. Output

- **stdout**: Compact counts, one line per category
- **markdown**: Grouped by status, with per-reference match details and field diffs
- **html**: Color-coded cards with dark/light mode support, no external dependencies

## Year discrepancies

When the local year differs from the online record by exactly 1 year, the tool notes this as a potential online-first vs. print publication difference. This is common: a paper may be published online in December 2019 but appear in the January 2020 print issue.

Known examples from test data:
- VOSviewer (doi:10.1007/s11192-009-0146-3): DOI landing page shows 2010, OpenAlex records 2009
- CiteSpace II (doi:10.1002/asi.20317): published 2006, OpenAlex records 2005
- Gusenbauer (pubmed:31614060): published 2020, online-first 2019

These references are accepted as auto-correctable rather than flagged as errors, with the year discrepancy noted in the output.

## Journal abbreviation database

The tool ships with a 41K+ journal abbreviation database (`hallubib/data/journal_abbrevs.csv.gz`) sourced from JabRef's open abbreviation lists. This enables fuzzy matching between abbreviated and full journal names.

To rebuild the database:
```bash
python scripts/build_journal_abbrevs.py
```

## Caching

API responses are cached in `~/.cache/hallubib/` (respects `$XDG_CACHE_HOME`) with a 30-day TTL. This avoids redundant network requests across runs.

```bash
hallubib --clear-cache
```

## Dependencies

Only one runtime dependency:
- [`requests`](https://docs.python-requests.org/) — HTTP client for API calls

## Features

- Parses both `.bib` (structured BibTeX) and `.tex` (`\bibitem` free-text) formats
- Verifies against OpenAlex, Semantic Scholar, Crossref, and arXiv with DOI cross-validation
- Crossref fallback and wider search for papers not found initially
- URL-only reference detection with reachability validation (GitHub, websites)
- GitHub repository and arXiv detection as extensible special cases (`special.py`)
- Concurrent API lookups via thread pool
- Disk caching with configurable TTL
- Three output formats: terminal summary, markdown, styled HTML
- HTML report with dark/light mode support
- LaTeX accent/unicode normalization for author and title comparison
- 41K+ journal abbreviation database from JabRef
- Field diffs classified as corrections vs. supplements
- Year discrepancy detection (online-first vs. print)

## Known Limitations & TODOs

- [ ] **"et al." handling in verification**: When a `.bib` entry uses `and others`, only the listed authors are compared. The matcher should weight first-author more heavily in these cases (partially implemented).
- [ ] **Minor misspellings in names**: Author name comparison strips accents and compares last names, but does not do fuzzy/edit-distance matching on names. A Levenshtein threshold could catch `Thomson` vs `Thompson`.
- [ ] **Auto-apply corrections**: Add a `--fix` flag that writes corrected entries back to the `.bib` file.
- [ ] **Rate limiting**: API sources are polled concurrently with a thread pool cap of 6. For very large bibliographies (100+ entries), more sophisticated rate limiting or backoff may be needed.
- [ ] **`\cite{}` extraction from `.tex`**: Currently only `\bibitem` entries in `thebibliography` environments are parsed. Support for `\cite{key}` + external `.bib` file resolution is not yet implemented.
- [ ] **BibTeX output mode**: Generate a corrected `.bib` file with suggested fixes applied.
- [ ] **Hard-to-find papers**: Some papers remain hard to find across all sources. In test data, `mongell91` (Mongell & Roth, "Sorority rush as a two-sided matching mechanism", Am. Econ. Rev. 1991) could not be matched by any source.

## Possible future sources

Additional APIs that could improve coverage further:

| Source | Notes |
|--------|-------|
| **DBLP** | Free, no auth. CS-only (~6M entries). Useful if targeting CS bibliographies. |
| **PubMed / NCBI E-utilities** | Free (3 RPS with API key). Biomedical only. |
| **OpenCitations** | Free, fully open. Citation graph metadata, less useful for discovery by title. |
| **Scopus** | Broad coverage (~90M records), but requires institutional API key. |
| **Google Scholar** | Best coverage overall, but no API — scraping violates TOS. |
| **JSTOR** | No free public lookup API. Data for Research (DfR) is bulk-download only; XML Gateway requires institutional license. |

## Running tests

```bash
uv run pytest                          # offline tests
uv run pytest -m network               # include network integration tests
```

## License

MIT
