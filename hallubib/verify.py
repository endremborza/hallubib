"""Match references against online records and categorize the results."""

import re
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import get_config
from .matching import (
    author_overlap,
    first_author_match,
    journal_similarity,
    title_similarity,
)
from .sources import (
    SourceError,
    search_arxiv,
    search_crossref,
    search_openalex_doi,
    search_openalex_title,
    search_semscholar,
    validate_doi,
)
from .sources._http import session
from .special import (
    detect_source_type,
    ignorable_supplements_for,
    is_url_only_reference,
    validate_url,
)
from .types import (
    CheckResult,
    DiffKind,
    FieldDiff,
    MatchEvidence,
    OnlineRecord,
    Reference,
    SourceAttempt,
    Status,
)


def _evidence(ref: Reference, c: OnlineRecord) -> tuple[float, MatchEvidence]:
    tsim = title_similarity(ref.title, c.title)
    asim = author_overlap(ref.authors, c.authors)
    year_ok = not ref.year or not c.year or abs(ref.year - c.year) <= 1
    score = tsim * 0.5 + asim * 0.3 + (0.2 if year_ok else 0.0)
    ev = MatchEvidence(
        title_sim=tsim,
        author_overlap=asim,
        first_author_match=first_author_match(ref.authors, c.authors),
        year_ok=year_ok,
        journal_sim=journal_similarity(ref.journal, c.journal),
    )
    return score, ev


def _compute_diffs(ref: Reference, rec: OnlineRecord) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    for field_name in ("title", "year", "journal", "volume", "number", "pages", "doi"):
        local = getattr(ref, field_name)
        online = getattr(rec, field_name)
        if local is None and online is None:
            continue
        lstr = str(local) if local is not None else None
        ostr = str(online) if online is not None else None
        if lstr == ostr:
            continue
        if lstr is not None and ostr is None:
            continue
        if field_name == "title" and lstr and ostr:
            if title_similarity(lstr, ostr) > 0.95:
                continue
        if field_name == "journal" and lstr and ostr:
            if journal_similarity(lstr, ostr) > 0.9:
                continue
        if field_name == "pages" and lstr and ostr:
            norm_l = re.sub(r"[-–—]+", "-", lstr).replace(" ", "")
            norm_o = re.sub(r"[-–—]+", "-", ostr).replace(" ", "")
            if norm_l == norm_o:
                continue
        kind = DiffKind.SUPPLEMENT if lstr is None else DiffKind.CORRECTION
        diffs.append(FieldDiff(field_name, lstr, ostr, kind))
    return diffs


def categorize(ref: Reference, candidates: list[OnlineRecord]) -> CheckResult:
    if not candidates:
        return CheckResult(
            reference=ref,
            status=Status.UNKNOWN,
            notes=["No matching records found online"],
        )

    scored = sorted(
        ((_evidence(ref, c), c) for c in candidates),
        key=lambda pair: (-pair[0][0], pair[1].title, pair[1].source),
    )
    (score, ev), best = scored[0]
    alternatives = [c for _, c in scored[1:]]

    diffs = _compute_diffs(ref, best)
    suggestions = {d.field_name: d.online_value for d in diffs if d.online_value}

    notes: list[str] = []
    for d in diffs:
        if d.field_name == "year" and d.kind == DiffKind.CORRECTION:
            if d.local_value and d.online_value:
                try:
                    if abs(int(d.local_value) - int(d.online_value)) == 1:
                        notes.append(
                            "Year difference may be due to online-first vs. print"
                        )
                except ValueError:
                    pass

    common = {
        "reference": ref,
        "best_match": best,
        "score": score,
        "evidence": ev,
        "alternatives": alternatives,
    }

    if (
        ev.title_sim >= 0.90
        and ev.first_author_match
        and ev.year_ok
        and (ev.journal_sim >= 0.8 or not ref.journal)
    ):
        ignorable = ignorable_supplements_for(ref)
        corrections = [d for d in diffs if d.kind == DiffKind.CORRECTION]
        significant_supplements = [
            d
            for d in diffs
            if d.kind == DiffKind.SUPPLEMENT and d.field_name not in ignorable
        ]
        status = (
            Status.VERIFIED
            if not corrections and not significant_supplements
            else Status.AUTO_CORRECTABLE
        )
        return CheckResult(
            status=status,
            diffs=diffs,
            suggestions=suggestions,
            notes=notes,
            **common,
        )

    if ev.title_sim >= 0.70 or (ev.first_author_match and ev.title_sim >= 0.50):
        if ev.title_sim < 0.90:
            notes.append(f"Title similarity: {ev.title_sim:.0%}")
        if not ev.first_author_match:
            notes.append("First author mismatch")
        if not ev.year_ok:
            notes.append(f"Year mismatch: local={ref.year}, online={best.year}")
        return CheckResult(
            status=Status.NEEDS_ATTENTION,
            diffs=diffs,
            suggestions=suggestions,
            notes=notes,
            **common,
        )

    return CheckResult(
        status=Status.UNKNOWN,
        notes=[f"Best candidate title similarity: {ev.title_sim:.0%}"],
        **common,
    )


def _finalize(result: CheckResult, attempts: list[SourceAttempt]) -> CheckResult:
    result.attempts = attempts
    for a in attempts:
        if not a.ok:
            result.notes.append(f"{a.source} lookup failed: {a.error}")
    return result


def check_reference(ref: Reference) -> CheckResult:
    if is_url_only_reference(ref):
        return _check_url_reference(ref)

    attempts: list[SourceAttempt] = []
    candidates: list[OnlineRecord] = []

    def run(source: str, query: str, fn) -> list[OnlineRecord]:
        try:
            res = fn()
        except SourceError as e:
            attempts.append(SourceAttempt(source, query, ok=False, error=e.detail))
            return []
        recs = res if isinstance(res, list) else ([res] if res else [])
        attempts.append(SourceAttempt(source, query, ok=True, hits=len(recs)))
        return recs

    doi_invalid = False
    if ref.doi:
        doi = ref.doi
        try:
            doi_valid = validate_doi(doi)
            doi_invalid = not doi_valid
            attempts.append(SourceAttempt("doi", doi, ok=True, hits=int(doi_valid)))
        except SourceError as e:
            doi_valid = False
            attempts.append(SourceAttempt("doi", doi, ok=False, error=e.detail))
        if doi_valid:
            candidates += run(
                "openalex",
                f"doi:{doi}",
                lambda: search_openalex_doi(doi),
            )
            if candidates:
                result = categorize(ref, candidates)
                if result.status is Status.VERIFIED:
                    return _finalize(result, attempts)

    candidates += run(
        "openalex",
        f"title:{ref.title}",
        lambda: search_openalex_title(ref.title, ref.year),
    )

    first_author = ref.authors[0] if ref.authors else None
    is_arxiv = bool(ref.url and "arxiv" in ref.url.lower())
    if is_arxiv or not candidates:
        candidates += run(
            "arxiv",
            f"title:{ref.title}",
            lambda: search_arxiv(ref.title, first_author),
        )

    result = categorize(ref, candidates)
    if result.status not in (Status.VERIFIED, Status.AUTO_CORRECTABLE):
        extra = run(
            "crossref",
            f"title:{ref.title}",
            lambda: search_crossref(ref.title, first_author),
        )
        extra += run(
            "semanticscholar",
            f"title:{ref.title}",
            lambda: search_semscholar(ref.title, first_author),
        )
        if extra:
            candidates += extra
            result = categorize(ref, candidates)

    if result.status is Status.UNKNOWN and ref.year:
        wider = run(
            "openalex",
            f"title-any-year:{ref.title}",
            lambda: search_openalex_title(ref.title, ref.year, with_year_filter=False),
        )
        if wider:
            candidates += wider
            result = categorize(ref, candidates)

    if doi_invalid:
        result.notes.append(f"DOI does not resolve: {ref.doi}")
        # A title match cannot vouch for a DOI that resolves nowhere - that is
        # the hallucination this tool exists to catch, so it needs a human.
        if result.status in (Status.VERIFIED, Status.AUTO_CORRECTABLE):
            result.status = Status.NEEDS_ATTENTION
    return _finalize(result, attempts)


def _check_url_reference(ref: Reference) -> CheckResult:
    url = ref.url or ""
    source_type = detect_source_type(url)
    reachable = validate_url(url, session()) if url else False
    notes: list[str] = []
    if source_type == "github":
        notes.append(f"GitHub repository: {url}")
    elif source_type == "arxiv":
        notes.append(f"arXiv: {url}")
    else:
        notes.append(f"URL: {url}")
    notes.append("URL is reachable" if reachable else "URL is not reachable")
    return CheckResult(
        reference=ref,
        status=Status.URL_REFERENCE if reachable else Status.UNKNOWN,
        attempts=[SourceAttempt("url", url, ok=True, hits=int(reachable))],
        notes=notes,
    )


def check_references_iter(
    refs: Sequence[Reference],
    max_workers: int | None = None,
) -> Iterator[tuple[int, CheckResult]]:
    workers = max_workers or get_config().max_workers
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_reference, ref): i for i, ref in enumerate(refs)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                yield idx, fut.result()
            except Exception as e:
                yield (
                    idx,
                    CheckResult(
                        reference=refs[idx],
                        status=Status.UNKNOWN,
                        notes=[f"Error during verification: {e}"],
                    ),
                )


def check_references(
    refs: Sequence[Reference],
    max_workers: int | None = None,
) -> list[CheckResult]:
    results: list[CheckResult | None] = [None] * len(refs)
    for idx, result in check_references_iter(refs, max_workers):
        results[idx] = result
    return [r for r in results if r is not None]
