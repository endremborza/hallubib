# hallubib

[![pypi](https://img.shields.io/pypi/v/hallubib.svg)](https://pypi.org/project/hallubib/)

Check bibliography references for hallucinations. Parses `.bib` and `.tex` files, verifies each reference against online sources (OpenAlex, arXiv, DOI resolution), and categorizes them by confidence.

## Installation

```bash
# With uv (recommended)
uv tool install hallubib

# Or with pip
pip install hallubib
```

For development:
```bash
git clone https://github.com/endremborza/hallubib
cd hallubib
uv sync
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
2. **OpenAlex lookup**: Search by DOI (fast path) or by title (full-text search)
3. **arXiv search**: For arXiv-linked papers or as fallback when OpenAlex yields nothing

API calls run concurrently (thread pool) for speed.

### 3. Categorize

Each reference is assigned one of four statuses:

| Status | Meaning |
|--------|---------|
| **Verified** | Exact or near-exact match found; all fields consistent |
| **Auto-correctable** | Match found but some fields differ (e.g., volume, DOI, journal name) |
| **Needs attention** | Partial match — ambiguous, may be wrong edition or different paper |
| **Unknown** | No plausible match found online |

Matching uses:
- Title similarity (normalized, accent-stripped, fuzzy matching)
- First-author last name matching
- Year tolerance (±1 year for preprint/publication date differences)
- Journal name fuzzy matching with common abbreviation expansion

### 4. Output

- **stdout**: Compact counts, one line per category
- **markdown**: Grouped by status, with per-reference match details and field diffs
- **html**: Color-coded cards with inline CSS, no external dependencies

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
- Verifies against OpenAlex and arXiv with DOI cross-validation
- Concurrent API lookups via thread pool
- Disk caching with configurable TTL
- Three output formats: terminal summary, markdown, styled HTML
- LaTeX accent/unicode normalization for author and title comparison
- Journal abbreviation expansion for fuzzy matching
- HTML output auto-opens in default browser

## Known Limitations & TODOs

- [ ] **Journal abbreviation coverage**: Only a small hardcoded set of abbreviations is supported. A more comprehensive solution could pull from ISSN abbreviation databases.
- [ ] **"et al." handling in verification**: When a `.bib` entry uses `and others`, only the listed authors are compared. The matcher should weight first-author more heavily in these cases (partially implemented).
- [ ] **Minor misspellings in names**: Author name comparison strips accents and compares last names, but does not do fuzzy/edit-distance matching on names. A Levenshtein threshold could catch `Thomson` vs `Thompson`.
- [ ] **Missing bibliographic fields**: When a reference is missing volume/pages/DOI, the tool suggests additions from the online record. However, it does not yet generate a corrected `.bib` file — only reports diffs.
- [ ] **Auto-apply corrections**: Add a `--fix` flag that writes corrected entries back to the `.bib` file.
- [ ] **Crossref integration**: Add Crossref as an additional verification source for broader DOI/metadata coverage.
- [ ] **Rate limiting**: OpenAlex and arXiv are polled concurrently with a thread pool cap of 6. For very large bibliographies (100+ entries), more sophisticated rate limiting or backoff may be needed.
- [ ] **`\cite{}` extraction from `.tex`**: Currently only `\bibitem` entries in `thebibliography` environments are parsed. Support for `\cite{key}` + external `.bib` file resolution is not yet implemented.
- [ ] **Confidence scores in output**: Surface the title similarity percentage and author overlap in the detailed reports.
- [ ] **BibTeX output mode**: Generate a corrected `.bib` file with suggested fixes applied.

## Running tests

```bash
uv run pytest                          # offline tests
uv run pytest -m network               # include network integration tests
```

## License

MIT
