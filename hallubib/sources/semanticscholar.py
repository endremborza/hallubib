"""Semantic Scholar Graph API client: exact-match lookup and relevance search."""

from .. import cache
from ..config import get_config
from ..matching import author_last
from ..names import parse_name
from ..types import Name, OnlineRecord
from ._http import SourceError, request

_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = (
    "paperId,title,authors,year,journal,venue,externalIds,abstract,url,publicationTypes"
)
_TYPE_MAP = {
    "Book": "book",
    "BookSection": "chapter",
    "Conference": "paper-conference",
    "Dataset": "dataset",
    "JournalArticle": "article-journal",
    "Review": "article-journal",
}


def _headers() -> dict | None:
    key = get_config().s2_api_key
    return {"x-api-key": key} if key else None


def parse_paper(paper: dict) -> OnlineRecord | None:
    title = paper.get("title")
    if not title:
        return None
    authors = [
        parse_name(a["name"]) for a in paper.get("authors") or [] if a.get("name")
    ]
    ext_ids = paper.get("externalIds") or {}
    doi = ext_ids.get("DOI")
    journal_info = paper.get("journal") or {}
    ids: dict[str, str] = {}
    if paper.get("paperId"):
        ids["semanticscholar"] = paper["paperId"]
    if ext_ids.get("ArXiv"):
        ids["arxiv"] = ext_ids["ArXiv"]
    if doi:
        ids["doi"] = doi
    rec_type = None
    for pt in paper.get("publicationTypes") or []:
        if pt in _TYPE_MAP:
            rec_type = _TYPE_MAP[pt]
            break
    return OnlineRecord(
        source="semanticscholar",
        title=title,
        authors=authors,
        year=paper.get("year"),
        journal=journal_info.get("name") or paper.get("venue") or None,
        volume=journal_info.get("volume"),
        pages=journal_info.get("pages"),
        doi=doi,
        url=paper.get("url"),
        abstract=paper.get("abstract"),
        type=rec_type,
        ids=ids,
    )


def _run_search(endpoint: str, cache_tag: str, params: dict) -> list[OnlineRecord]:
    ck = cache.cache_key(f"{cache_tag}:{_FIELDS}")
    cached = cache.get("semscholar", ck)
    if cached is not None:
        papers = cached.get("data", [])
    else:
        r = request(
            "semanticscholar",
            f"{_BASE}/{endpoint}",
            params={**params, "fields": _FIELDS},
            headers=_headers(),
        )
        if r.status_code == 404:
            papers = []
        elif r.status_code != 200:
            raise SourceError("semanticscholar", f"HTTP {r.status_code}")
        else:
            papers = r.json().get("data", [])
        cache.put("semscholar", ck, {"data": papers})
    return [rec for p in papers if (rec := parse_paper(p))]


def search_match(title: str, first_author: Name | None = None) -> list[OnlineRecord]:
    query = title[:300]
    author_q = author_last(first_author) if first_author else ""
    return _run_search(
        "paper/search/match",
        f"semscholar:{query}:{author_q}",
        {"query": query},
    )


def search_relevance(query: str, limit: int = 10) -> list[OnlineRecord]:
    return _run_search(
        "paper/search",
        f"semscholar:relevance:{query[:300]}:{limit}",
        {"query": query[:300], "limit": limit},
    )
