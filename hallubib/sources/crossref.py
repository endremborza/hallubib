"""Crossref client."""

import re

from .. import cache
from ..matching import author_last
from ..types import Name, OnlineRecord
from ._http import SourceError, request

_BASE = "https://api.crossref.org"
_SELECT = (
    "title,author,issued,published-print,published-online,container-title,"
    "volume,issue,page,DOI,URL,abstract,type,publisher"
)
_TYPE_MAP = {
    "book": "book",
    "book-chapter": "chapter",
    "dataset": "dataset",
    "dissertation": "thesis",
    "edited-book": "book",
    "journal-article": "article-journal",
    "monograph": "book",
    "posted-content": "article",
    "proceedings-article": "paper-conference",
    "reference-book": "book",
    "reference-entry": "entry-encyclopedia",
    "report": "report",
    "standard": "standard",
}


def parse_item(item: dict) -> OnlineRecord | None:
    titles = item.get("title", [])
    if not titles:
        return None
    authors = []
    for a in item.get("author", []):
        if a.get("family"):
            authors.append(Name(family=a["family"], given=a.get("given", "")))
        elif a.get("name"):
            authors.append(Name(literal=a["name"]))
    year = None
    for date_field in ("published-print", "published-online", "issued"):
        date_info = item.get(date_field)
        if date_info:
            parts = date_info.get("date-parts", [[]])
            if parts and parts[0] and parts[0][0]:
                year = parts[0][0]
                break
    containers = item.get("container-title", [])
    doi = item.get("DOI")
    abstract = item.get("abstract")
    if abstract:
        abstract = re.sub(r"<[^>]+>", " ", abstract)
        abstract = re.sub(r"\s+", " ", abstract).strip() or None
    return OnlineRecord(
        source="crossref",
        title=titles[0],
        authors=authors,
        year=year,
        journal=containers[0] if containers else None,
        volume=item.get("volume"),
        number=item.get("issue"),
        pages=item.get("page"),
        doi=doi,
        url=item.get("URL"),
        abstract=abstract,
        type=_TYPE_MAP.get(item.get("type") or "", "document"),
        publisher=item.get("publisher"),
        ids={"doi": doi} if doi else {},
    )


def search(title: str, first_author: Name | None = None) -> list[OnlineRecord]:
    query = re.sub(r"[^\w\s]", "", title)[:200]
    author_q = author_last(first_author) if first_author else ""
    ck = cache.cache_key(f"crossref:{query}:{author_q}:{_SELECT}")
    cached = cache.get("crossref", ck)
    if cached is not None:
        items = cached.get("items", [])
    else:
        params: dict[str, str | int] = {
            "query.title": query,
            "rows": 5,
            "select": _SELECT,
        }
        if author_q:
            params["query.author"] = author_q
        r = request("crossref", f"{_BASE}/works", params=params)
        if r.status_code == 404:
            items = []
        elif r.status_code != 200:
            raise SourceError("crossref", f"HTTP {r.status_code}")
        else:
            items = r.json().get("message", {}).get("items", [])
        cache.put("crossref", ck, {"items": items})
    return [rec for item in items if (rec := parse_item(item))]
