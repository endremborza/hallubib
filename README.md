# hallubib

[![pypi](https://img.shields.io/pypi/v/hallubib.svg)](https://pypi.org/project/hallubib/)

Check bibliography references for hallucinations. Parses `.bib` and `.tex` files, verifies each reference against online sources (OpenAlex, Semantic Scholar, Crossref, arXiv, DOI resolution), and categorizes them by confidence. Fully typed (`py.typed`), one runtime dependency, usable as a CLI or as a library.

## Installation

```bash
# With uv (recommended)
uv tool install hallubib
# Or with pip
pip install hallubib
```

## CLI usage

```bash
# Quick summary (default)
hallubib references.bib

# Detailed markdown report
hallubib paper.tex --output=md

# HTML report (opens in browser)
hallubib references.bib --output=html

# Machine-readable check results (versioned JSON)
hallubib references.bib --output=json

# Convert to CSL-JSON without checking anything (offline)
hallubib references.bib --output=csl

# Join the polite pools (or set HALLUBIB_MAILTO)
hallubib references.bib --mailto=you@example.org

# Clear the cache
hallubib --clear-cache
```

| Flag | Description |
|------|-------------|
| `--output=stdout` | (default) Summary counts per category |
| `--output=md` | Detailed markdown breakdown to stdout |
| `--output=html` | Styled HTML report, opened in default browser |
| `--output=json` | Full check results as JSON, stamped with the hallubib version |
| `--output=csl` | CSL-JSON conversion of the parsed references, no network |

## Library usage

```python
import hallubib as hb

hb.configure(mailto="you@example.org")  # optional: cache_dir, timeout, max_workers, s2_api_key

refs = hb.parse_bib(open("refs.bib").read())

# Blocking, ordered:
results = hb.check_references(refs)

# Or as-completed, for progress reporting:
for idx, result in hb.check_references_iter(refs):
    print(refs[idx].key, result.status)

# CSL-JSON boundary: every reference or online record maps to a CSL item,
# and CSL items serialize back to BibTeX.
items = [hb.to_csl(r) for r in refs]
print(hb.to_bib(items))
```

Key types (all frozen dataclasses unless noted):

- `Reference` — a parsed local reference: `key`, CSL `type`, `title`, `authors: list[Name]`, bibliographic fields, and `extra` (every bib field with no first-class slot; nothing is dropped).
- `Name(family, given, literal)` — structured names; `literal` holds corporate authors. Particles (`van der Waals`) and suffixes survive parsing.
- `OnlineRecord` — a record from one source, carrying `ids` (source-native identifiers: OpenAlex work id, S2 paperId, arXiv id, DOI), `url`, `abstract`, CSL `type`, and `publisher` alongside the core fields.
- `CheckResult` (mutable) — `status`, `best_match`, `score`, `evidence` (title/author/year/journal similarity detail), `diffs`, `suggestions`, `alternatives` (every non-best candidate, best-first), `attempts` (one `SourceAttempt` per lookup: which source, what query, whether it succeeded, how many hits), `notes`.

`results_to_dict(results)` turns results into a JSON-ready dict stamped with `hallubib_version`; enums are `StrEnum`s and ordering is deterministic, so serialized results diff cleanly in git.

## How it works

### 1. Parse

- **`.bib`**: full BibTeX parsing with LaTeX accent normalization, brace-aware author splitting, bare/quoted/braced field values. Entry types map to CSL types (`@inproceedings` → `paper-conference`); unrecognized fields are kept in `Reference.extra`.
- **`.tex`**: `\bibitem` entries from `thebibliography` environments via `parse_tex`, built on the public `parse_bibitem(key, raw_text)`. Handles `\bibitem[label]{key}`, `\newblock`-structured entries, APA-style author/year lines, and a missing `\end{thebibliography}`.

### 2. Verify

Each reference is checked against online sources in this order:

1. **DOI validation**: a present DOI is checked for registration against `doi.org` (redirect response, no landing-page crawl)
2. **OpenAlex lookup**: by DOI (fast path), then by title (full-text search with ±1 year filter) — the title search runs even when the DOI matched but did not fully verify
3. **arXiv search**: for arXiv-linked papers or as fallback when OpenAlex yields nothing
4. **Crossref + Semantic Scholar fallback**: if not yet verified/auto-correctable, search both for broader coverage
5. **Wider search**: if still unknown, retry OpenAlex without year filter

URL-only references (GitHub repos, websites) are validated for reachability instead of bibliographic matching.

The source clients live in `hallubib.sources` and are usable directly (`search_openalex_title`, `search_semscholar`, `search_semscholar_relevance` for discovery, …). All requests go through a shared layer with per-host pacing, retry with `Retry-After`-aware backoff on 429/5xx, and a `SourceError` raised on persistent failure — so a real reference is never called hallucinated just because a source was down: failed lookups land in `CheckResult.attempts` and the notes, distinct from "searched and found nothing".

Lookups run concurrently (thread pool, `Config.max_workers`).

### 3. Categorize

Each reference is assigned one of five statuses:

| Status | Meaning |
|--------|---------|
| **Unknown** | No plausible match found online |
| **Needs attention** | Partial match — ambiguous, may be wrong edition or different paper |
| **Auto-correctable** | Match found but some fields differ (e.g., volume, year, journal name) |
| **URL reference** | Not a traditional article — URL validated for reachability |
| **Verified** | Match found; all fields consistent or only missing optional info (DOI, issue number) |

Matching uses title similarity (normalized, accent-stripped), first-author family-name matching, year tolerance (±1 for preprint/print differences), and journal fuzzy matching against a 41K+ abbreviation database. The full similarity breakdown survives on `CheckResult.evidence`, the composite on `score`, and every non-best candidate on `alternatives` — notes are derived text, not the data.

Field differences are classified as **corrections** (local conflicts with online) or **supplements** (local missing, online has it).

### 4. Output

Terminal summary, markdown, styled HTML (dark/light), versioned JSON, or CSL-JSON. Output is ordered most-problematic-first.

## CSL-JSON and BibTeX round-trip

CSL-JSON is the boundary format: `to_csl(ref_or_record, key=None)` and `from_csl(item)` own the domain mapping (BibTeX entry types ↔ CSL types, `booktitle` → `container-title`, date-parts, structured names, `school`/`institution` ↔ `publisher` by type). `to_bib(items)` serializes CSL items back to BibTeX deterministically. Fields with no CSL mapping ride in the item's `custom` object and are re-emitted by `to_bib` — round-tripping a `.bib` through CSL-JSON preserves the full field set, so a CSL-JSON store can be the canonical form with every `.bib` derived from it.

## Configuration

`configure(...)` swaps a frozen `Config`: `mailto` (polite pools; also `HALLUBIB_MAILTO`), `cache_dir`, `cache_ttl_days`, `timeout`, `max_workers`, `s2_api_key` (also `S2_API_KEY`), `openalex_api_key` (also `OPENALEX_API_KEY`).

Set `mailto`. It is nominally optional, but OpenAlex's anonymous pool is a daily credit budget rather than a rate limit — exhaust it and every request comes back `429` with a `Retry-After` measured in hours, for the rest of the day. `s2_api_key` does the same for Semantic Scholar, which throttles unauthenticated callers hard enough that a single bibliography can trip it. `openalex_api_key`, if you have one, supersedes the mailto pool entirely.

Retries are automatic for `429`, `500`, `502` and `503`: three attempts, honouring `Retry-After` when the server sends one and backing off exponentially when it does not. A `Retry-After` longer than 30s is not slept through — it means a quota, not congestion, so the request fails immediately with `SourceError("rate limited, retry after Ns")` instead of stalling the caller and spending more of the budget. `check_reference` records that as a failed `SourceAttempt`, so a throttled source degrades the result rather than aborting the run.

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

API responses are cached in `~/.cache/hallubib/` (respects `$XDG_CACHE_HOME` and `Config.cache_dir`) with a 30-day TTL. Writes are atomic, so concurrent runs never read partial files.

```bash
hallubib --clear-cache
```

## Dependencies

Only one runtime dependency:
- [`requests`](https://docs.python-requests.org/) — HTTP client for API calls

## Known Limitations & TODOs

- [ ] **"et al." handling in verification**: When a `.bib` entry uses `and others`, only the listed authors are compared. The matcher should weight first-author more heavily in these cases (partially implemented).
- [ ] **Minor misspellings in names**: Author name comparison strips accents and compares family names, but does not do fuzzy/edit-distance matching on names. A Levenshtein threshold could catch `Thomson` vs `Thompson`.
- [ ] **Auto-apply corrections**: Add a `--fix` flag that writes corrected entries back to the `.bib` file (the pieces exist: `suggestions` + `to_csl` + `to_bib`).
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
uv run pytest                            # offline, ~2s — what CI runs on every push
uv run pytest --run-network              # everything, offline + the live drift canary
uv run python -m tests.record_cassettes  # re-record the API fixtures (needs network)
```

The offline suite is the whole pipeline: `tests/fixtures/golden.bib` holds one reference per route through `verify.check_reference` (valid DOI, unregistered DOI, arXiv preprint, book, chapter, wrong volume, wrong year, invented paper, three URL-only forms), and `tests/fixtures/cassettes/golden.json` holds the real API responses each of them provoked. Replay intercepts `sources._http.request`, so every source client still runs its own cache lookup, status handling, parsing and cache write against genuine payloads — no socket, no fixtures written by hand.

`tests/test_network.py` is the drift canary and is skipped without `--run-network`. It exists for the one failure replay structurally cannot see: a source changing its schema, matching or coverage. It runs weekly in CI (`.github/workflows/drift.yml`) rather than on pull requests, so an upstream outage never blocks a merge, and it distinguishes drift from throttling — a reference whose lookups degraded is reported and skipped, not failed.

Re-record whenever a source's schema moves. The recorder uses a cold cache, merges into the existing cassette, and never lets a throttled retry demote an interaction already on disk, so it is safe to run repeatedly until every call lands.

## License

MIT
