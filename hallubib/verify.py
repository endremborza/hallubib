"""Verify references against OpenAlex, arXiv, and DOI resolution."""

import re
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

import requests

from . import cache
from .types import CheckResult, FieldDiff, OnlineRecord, Reference, Status

_SESSION: requests.Session | None = None
_OPENALEX_BASE = "https://api.openalex.org"
_ARXIV_BASE = "http://export.arxiv.org/api/query"


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers["User-Agent"] = "hallubib/0.1 (bibliography checker)"
    return _SESSION


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _norm(s: str) -> str:
    s = _strip_accents(s.lower())
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _title_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _author_last(name: str) -> str:
    if "," in name:
        return _norm(name.split(",")[0])
    parts = name.split()
    return _norm(parts[-1]) if parts else ""


def _first_author_match(ref_authors: list[str], online_authors: list[str]) -> bool:
    if not ref_authors or not online_authors:
        return not ref_authors and not online_authors
    return _author_last(ref_authors[0]) == _author_last(online_authors[0])


def _author_overlap(ref_authors: list[str], online_authors: list[str]) -> float:
    if not ref_authors or not online_authors:
        return 1.0 if not ref_authors and not online_authors else 0.0
    ref_lasts = {_author_last(a) for a in ref_authors}
    online_lasts = {_author_last(a) for a in online_authors}
    if not ref_lasts or not online_lasts:
        return 0.0
    intersection = ref_lasts & online_lasts
    return len(intersection) / min(len(ref_lasts), len(online_lasts))


# --- DOI ---

def validate_doi(doi: str) -> bool:
    ck = cache.cache_key(f"doi:{doi}")
    cached = cache.get("doi", ck)
    if cached is not None:
        return cached.get("valid", False)
    try:
        r = _session().head(
            f"https://doi.org/{doi}", allow_redirects=True, timeout=10
        )
        valid = r.status_code < 400
    except requests.RequestException:
        valid = False
    cache.put("doi", ck, {"valid": valid})
    return valid


# --- OpenAlex ---

def _parse_openalex_work(w: dict) -> OnlineRecord | None:
    title = w.get("title") or w.get("display_name")
    if not title:
        return None
    title = re.sub(r"<[^>]+>", "", title)
    authors = []
    for auth in w.get("authorships", []):
        name = auth.get("author", {}).get("display_name")
        if name:
            parts = name.split()
            if len(parts) >= 2:
                authors.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
            else:
                authors.append(name)
    doi_raw = w.get("doi") or ""
    doi = re.sub(r"^https?://doi\.org/", "", doi_raw) if doi_raw else None
    loc = w.get("primary_location") or {}
    source = loc.get("source") or {}
    journal = source.get("display_name")
    bib = w.get("biblio") or {}
    return OnlineRecord(
        source="openalex",
        title=title,
        authors=authors,
        year=w.get("publication_year"),
        journal=journal,
        volume=bib.get("volume"),
        number=bib.get("issue"),
        pages=f"{bib['first_page']}-{bib['last_page']}"
        if bib.get("first_page") and bib.get("last_page") else None,
        doi=doi,
    )


def search_openalex_doi(doi: str) -> OnlineRecord | None:
    ck = cache.cache_key(f"openalex:doi:{doi}")
    cached = cache.get("openalex", ck)
    if cached is not None:
        return _parse_openalex_work(cached) if cached.get("title") else None
    try:
        r = _session().get(
            f"{_OPENALEX_BASE}/works/doi:{doi}",
            params={"select": "title,display_name,authorships,doi,publication_year,primary_location,biblio"},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        cache.put("openalex", ck, data)
        return _parse_openalex_work(data)
    except requests.RequestException:
        return None


def search_openalex_title(title: str, year: int | None = None) -> list[OnlineRecord]:
    query = re.sub(r"[^\w\s]", "", title)[:200]
    ck = cache.cache_key(f"openalex:title:{query}:{year}")
    cached = cache.get("openalex", ck)
    if cached is not None:
        works = cached.get("results", [])
    else:
        try:
            params: dict[str, str | int] = {
                "search": query,
                "per_page": 5,
                "select": "title,display_name,authorships,doi,publication_year,primary_location,biblio",
            }
            if year:
                params["filter"] = f"publication_year:{year - 1}-{year + 1}"
            r = _session().get(
                f"{_OPENALEX_BASE}/works", params=params, timeout=15
            )
            if r.status_code != 200:
                return []
            data = r.json()
            works = data.get("results", [])
            cache.put("openalex", ck, data)
        except requests.RequestException:
            return []
    records = []
    for w in works:
        rec = _parse_openalex_work(w)
        if rec:
            records.append(rec)
    return records


# --- arXiv ---

_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


def search_arxiv(title: str, first_author: str | None = None) -> list[OnlineRecord]:
    query_parts = [f'ti:"{title[:100]}"']
    if first_author:
        last = _author_last(first_author)
        if last:
            query_parts.append(f"au:{last}")
    query = "+AND+".join(query_parts)
    ck = cache.cache_key(f"arxiv:{query}")
    cached = cache.get("arxiv", ck)
    if cached is not None:
        entries_raw = cached.get("entries", [])
    else:
        try:
            r = _session().get(
                _ARXIV_BASE,
                params={"search_query": " AND ".join(query_parts), "max_results": "3"},
                timeout=15,
            )
            if r.status_code != 200:
                return []
            root = ET.fromstring(r.text)
            entries_raw = []
            for entry in root.findall("atom:entry", _ARXIV_NS):
                t = entry.findtext("atom:title", "", _ARXIV_NS).strip()
                t = re.sub(r"\s+", " ", t)
                authors = [
                    a.findtext("atom:name", "", _ARXIV_NS)
                    for a in entry.findall("atom:author", _ARXIV_NS)
                ]
                year_text = entry.findtext("atom:published", "", _ARXIV_NS)
                year = int(year_text[:4]) if year_text and len(year_text) >= 4 else None
                doi_el = entry.find("atom:link[@title='doi']", _ARXIV_NS)
                doi = None
                if doi_el is not None:
                    href = doi_el.get("href", "")
                    doi = re.sub(r"^https?://doi\.org/", "", href) if href else None
                entries_raw.append({
                    "title": t, "authors": authors, "year": year, "doi": doi,
                })
            cache.put("arxiv", ck, {"entries": entries_raw})
        except (requests.RequestException, ET.ParseError):
            return []

    records = []
    for e in entries_raw:
        auth_list = []
        for a in e.get("authors", []):
            parts = a.split()
            if len(parts) >= 2:
                auth_list.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
            else:
                auth_list.append(a)
        records.append(OnlineRecord(
            source="arxiv",
            title=e["title"],
            authors=auth_list,
            year=e.get("year"),
            doi=e.get("doi"),
        ))
    return records


# --- Matcher ---

JOURNAL_ABBREVS: dict[str, str] = {
    "j. econ. theory": "journal of economic theory",
    "am. econ. rev.": "american economic review",
    "amer. math. monthly": "american mathematical monthly",
    "j. polit. econ.": "journal of political economy",
    "rev. econ. stat.": "review of economics and statistics",
    "j. algorithms": "journal of algorithms",
    "games econ. behav.": "games and economic behavior",
    "manage. sci.": "management science",
    "soc. choice welfare": "social choice and welfare",
    "j. math. econ.": "journal of mathematical economics",
    "j. appl. soc. psychol.": "journal of applied social psychology",
    "j. housing econ.": "journal of housing economics",
    "reg. sci. urban econ.": "regional science and urban economics",
    "annu. rev. public health": "annual review of public health",
    "annu. rev. sociol.": "annual review of sociology",
    "inf. process. lett.": "information processing letters",
    "discret. appl. math.": "discrete applied mathematics",
    "theor. comput. sci.": "theoretical computer science",
    "appl. opt.": "applied optics",
}


def _norm_journal(j: str | None) -> str:
    if not j:
        return ""
    n = _norm(j)
    return JOURNAL_ABBREVS.get(n, n)


def _journal_sim(a: str | None, b: str | None) -> float:
    na, nb = _norm_journal(a), _norm_journal(b)
    if not na or not nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _compute_diffs(ref: Reference, rec: OnlineRecord) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    for field_name in ("title", "year", "journal", "volume", "number", "pages", "doi"):
        local = getattr(ref, field_name)
        online = getattr(rec, field_name)
        if local is None and online is None:
            continue
        lstr = str(local) if local is not None else None
        ostr = str(online) if online is not None else None
        if lstr != ostr and not (
            field_name == "title" and lstr and ostr and _title_sim(lstr, ostr) > 0.95
        ):
            if field_name == "journal" and lstr and ostr and _journal_sim(lstr, ostr) > 0.9:
                continue
            if field_name == "pages" and lstr and ostr:
                norm_l = re.sub(r"[-–—]+", "-", lstr).replace(" ", "")
                norm_o = re.sub(r"[-–—]+", "-", ostr).replace(" ", "")
                if norm_l == norm_o:
                    continue
            diffs.append(FieldDiff(field_name, lstr, ostr))
    return diffs


def categorize(ref: Reference, candidates: list[OnlineRecord]) -> CheckResult:
    if not candidates:
        return CheckResult(
            reference=ref, status=Status.UNKNOWN,
            notes=["No matching records found online"],
        )

    best: OnlineRecord | None = None
    best_score = 0.0
    for c in candidates:
        tsim = _title_sim(ref.title, c.title)
        asim = _author_overlap(ref.authors, c.authors)
        ysim = 1.0 if (not ref.year or not c.year or abs(ref.year - c.year) <= 1) else 0.0
        score = tsim * 0.5 + asim * 0.3 + ysim * 0.2
        if score > best_score:
            best_score = score
            best = c

    if best is None:
        return CheckResult(
            reference=ref, status=Status.UNKNOWN,
            notes=["No matching records found online"],
        )

    tsim = _title_sim(ref.title, best.title)
    fa_match = _first_author_match(ref.authors, best.authors)
    jsim = _journal_sim(ref.journal, best.journal)
    year_ok = not ref.year or not best.year or abs(ref.year - best.year) <= 1

    diffs = _compute_diffs(ref, best)
    suggestions = {d.field_name: d.online_value for d in diffs if d.online_value}

    if tsim >= 0.90 and fa_match and year_ok and (jsim >= 0.8 or not ref.journal):
        if not diffs:
            return CheckResult(reference=ref, status=Status.VERIFIED, best_match=best)
        return CheckResult(
            reference=ref, status=Status.AUTO_CORRECTABLE,
            best_match=best, diffs=diffs, suggestions=suggestions,
        )

    if tsim >= 0.70 or (fa_match and tsim >= 0.50):
        notes: list[str] = []
        if tsim < 0.90:
            notes.append(f"Title similarity: {tsim:.0%}")
        if not fa_match:
            notes.append("First author mismatch")
        if not year_ok:
            notes.append(f"Year mismatch: local={ref.year}, online={best.year}")
        return CheckResult(
            reference=ref, status=Status.NEEDS_ATTENTION,
            best_match=best, diffs=diffs, suggestions=suggestions, notes=notes,
        )

    return CheckResult(
        reference=ref, status=Status.UNKNOWN, best_match=best,
        notes=[f"Best candidate title similarity: {tsim:.0%}"],
    )


# --- Orchestration ---

def _check_one(ref: Reference) -> CheckResult:
    candidates: list[OnlineRecord] = []

    if ref.doi:
        if validate_doi(ref.doi):
            rec = search_openalex_doi(ref.doi)
            if rec:
                candidates.append(rec)
                result = categorize(ref, candidates)
                if result.status == Status.VERIFIED:
                    return result

    if not candidates:
        candidates.extend(search_openalex_title(ref.title, ref.year))

    is_arxiv = ref.url and "arxiv" in ref.url.lower()
    if is_arxiv or not candidates:
        first_author = ref.authors[0] if ref.authors else None
        candidates.extend(search_arxiv(ref.title, first_author))

    return categorize(ref, candidates)


def check_references(refs: list[Reference], max_workers: int = 6) -> list[CheckResult]:
    results: list[CheckResult] = [None] * len(refs)  # type: ignore[list-item]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_check_one, ref): i for i, ref in enumerate(refs)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                results[idx] = fut.result()
            except Exception as e:
                results[idx] = CheckResult(
                    reference=refs[idx], status=Status.UNKNOWN,
                    notes=[f"Error during verification: {e}"],
                )
    return results
