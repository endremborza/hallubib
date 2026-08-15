"""OpenAlex client."""

import re

from .. import cache
from ..names import parse_name
from ..types import OnlineRecord
from ._http import SourceError, request

_BASE = "https://api.openalex.org"
_SELECT = (
    "id,title,display_name,authorships,doi,publication_year,"
    "primary_location,biblio,type,abstract_inverted_index"
)
_TYPE_MAP = {
    "article": "article-journal",
    "book": "book",
    "book-chapter": "chapter",
    "dataset": "dataset",
    "dissertation": "thesis",
    "editorial": "article-journal",
    "letter": "article-journal",
    "monograph": "book",
    "preprint": "article",
    "reference-entry": "entry-encyclopedia",
    "report": "report",
    "review": "article-journal",
    "standard": "standard",
}


def _deinvert(inv: dict | None) -> str | None:
    if not inv:
        return None
    positions = sorted((p, w) for w, ps in inv.items() for p in ps)
    return " ".join(w for _, w in positions) or None


def parse_work(w: dict) -> OnlineRecord | None:
    title = w.get("title") or w.get("display_name")
    if not title:
        return None
    title = re.sub(r"<[^>]+>", "", title)
    authors = []
    for auth in w.get("authorships", []):
        name = auth.get("author", {}).get("display_name")
        if name:
            authors.append(parse_name(name))
    doi_raw = w.get("doi") or ""
    doi = re.sub(r"^https?://doi\.org/", "", doi_raw) if doi_raw else None
    loc = w.get("primary_location") or {}
    source = loc.get("source") or {}
    bib = w.get("biblio") or {}
    ids: dict[str, str] = {}
    if w.get("id"):
        ids["openalex"] = str(w["id"]).rsplit("/", 1)[-1]
    if doi:
        ids["doi"] = doi
    return OnlineRecord(
        source="openalex",
        title=title,
        authors=authors,
        year=w.get("publication_year"),
        journal=source.get("display_name"),
        volume=bib.get("volume"),
        number=bib.get("issue"),
        pages=f"{bib['first_page']}-{bib['last_page']}"
        if bib.get("first_page") and bib.get("last_page")
        else None,
        doi=doi,
        url=loc.get("landing_page_url") or (doi_raw or None),
        abstract=_deinvert(w.get("abstract_inverted_index")),
        type=_TYPE_MAP.get(w.get("type") or "", "document"),
        publisher=source.get("host_organization_name"),
        ids=ids,
    )


def search_doi(doi: str) -> OnlineRecord | None:
    ck = cache.cache_key(f"openalex:doi:{doi}:{_SELECT}")
    cached = cache.get("openalex", ck)
    if cached is not None:
        return parse_work(cached) if cached.get("title") else None
    r = request(
        "openalex",
        f"{_BASE}/works/doi:{doi}",
        params={"select": _SELECT},
    )
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise SourceError("openalex", f"HTTP {r.status_code}")
    data = r.json()
    cache.put("openalex", ck, data)
    return parse_work(data)


def search_title(
    title: str,
    year: int | None = None,
    *,
    with_year_filter: bool = True,
) -> list[OnlineRecord]:
    query = re.sub(r"[^\w\s]", "", title)[:200]
    yr_key = year if with_year_filter else "any"
    ck = cache.cache_key(f"openalex:title:{query}:{yr_key}:{_SELECT}")
    cached = cache.get("openalex", ck)
    if cached is not None:
        works = cached.get("results", [])
    else:
        params: dict[str, str | int] = {
            "search": query,
            "per_page": 5,
            "select": _SELECT,
        }
        if year and with_year_filter:
            params["filter"] = f"publication_year:{year - 1}-{year + 1}"
        r = request("openalex", f"{_BASE}/works", params=params)
        if r.status_code != 200:
            raise SourceError("openalex", f"HTTP {r.status_code}")
        data = r.json()
        works = data.get("results", [])
        cache.put("openalex", ck, data)
    return [rec for w in works if (rec := parse_work(w))]
