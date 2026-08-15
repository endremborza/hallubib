"""arXiv Atom API client."""

import re
import xml.etree.ElementTree as ET

from .. import cache
from ..matching import author_last
from ..names import parse_name
from ..types import Name, OnlineRecord
from ._http import SourceError, request

_BASE = "http://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _parse_entry(entry: ET.Element) -> dict:
    title = re.sub(r"\s+", " ", entry.findtext("atom:title", "", _NS).strip())
    authors = [
        a.findtext("atom:name", "", _NS) for a in entry.findall("atom:author", _NS)
    ]
    year_text = entry.findtext("atom:published", "", _NS)
    year = int(year_text[:4]) if year_text and len(year_text) >= 4 else None
    doi_el = entry.find("atom:link[@title='doi']", _NS)
    doi = None
    if doi_el is not None:
        href = doi_el.get("href", "")
        doi = re.sub(r"^https?://doi\.org/", "", href) if href else None
    entry_id = entry.findtext("atom:id", "", _NS).strip()
    arxiv_id = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else None
    abstract = re.sub(r"\s+", " ", entry.findtext("atom:summary", "", _NS).strip())
    return {
        "title": title,
        "authors": authors,
        "year": year,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "url": entry_id or None,
        "abstract": abstract or None,
    }


def _to_record(e: dict) -> OnlineRecord:
    ids: dict[str, str] = {}
    if e.get("arxiv_id"):
        ids["arxiv"] = e["arxiv_id"]
    if e.get("doi"):
        ids["doi"] = e["doi"]
    return OnlineRecord(
        source="arxiv",
        title=e["title"],
        authors=[parse_name(a) for a in e.get("authors", []) if a],
        year=e.get("year"),
        doi=e.get("doi"),
        url=e.get("url"),
        abstract=e.get("abstract"),
        type="article",
        ids=ids,
    )


def search(title: str, first_author: Name | None = None) -> list[OnlineRecord]:
    query_parts = [f'ti:"{title[:100]}"']
    if first_author:
        last = author_last(first_author)
        if last:
            query_parts.append(f"au:{last}")
    ck = cache.cache_key(f"arxiv:{'+AND+'.join(query_parts)}")
    cached = cache.get("arxiv", ck)
    if cached is not None:
        entries = cached.get("entries", [])
    else:
        r = request(
            "arxiv",
            _BASE,
            params={"search_query": " AND ".join(query_parts), "max_results": "3"},
        )
        if r.status_code != 200:
            raise SourceError("arxiv", f"HTTP {r.status_code}")
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError as e:
            raise SourceError("arxiv", f"malformed response: {e}") from e
        entries = [_parse_entry(el) for el in root.findall("atom:entry", _NS)]
        cache.put("arxiv", ck, {"entries": entries})
    return [_to_record(e) for e in entries if e.get("title")]
