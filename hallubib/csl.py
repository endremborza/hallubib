"""CSL-JSON boundary: BibTeX/CSL type maps, to_csl and from_csl."""

from .names import split_authors
from .types import Name, OnlineRecord, Reference

BIB_TYPE_TO_CSL: dict[str, str] = {
    "article": "article-journal",
    "book": "book",
    "booklet": "pamphlet",
    "conference": "paper-conference",
    "dataset": "dataset",
    "electronic": "webpage",
    "inbook": "chapter",
    "incollection": "chapter",
    "inproceedings": "paper-conference",
    "manual": "report",
    "mastersthesis": "thesis",
    "misc": "document",
    "online": "webpage",
    "phdthesis": "thesis",
    "proceedings": "book",
    "software": "software",
    "techreport": "report",
    "unpublished": "manuscript",
}

CSL_TYPE_TO_BIB: dict[str, str] = {
    "article": "misc",
    "article-journal": "article",
    "article-magazine": "article",
    "article-newspaper": "article",
    "book": "book",
    "chapter": "incollection",
    "dataset": "misc",
    "document": "misc",
    "manuscript": "unpublished",
    "pamphlet": "booklet",
    "paper-conference": "inproceedings",
    "report": "techreport",
    "software": "misc",
    "thesis": "phdthesis",
    "webpage": "misc",
}

_EXTRA_TO_CSL: dict[str, str] = {
    "abstract": "abstract",
    "address": "publisher-place",
    "chapter": "chapter-number",
    "edition": "edition",
    "isbn": "ISBN",
    "issn": "ISSN",
    "keywords": "keyword",
    "language": "language",
    "note": "note",
    "series": "collection-title",
}
_CSL_TO_EXTRA: dict[str, str] = {v: k for k, v in _EXTRA_TO_CSL.items()}

_MONTHS = {
    m: i + 1
    for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())
}


def _parse_month(raw: str | None) -> int | None:
    if not raw:
        return None
    key = raw.strip().lower()
    if key.isdigit() and 1 <= int(key) <= 12:
        return int(key)
    return _MONTHS.get(key[:3])


def _name_to_csl(n: Name) -> dict:
    if n.literal:
        return {"literal": n.literal}
    d: dict = {"family": n.family}
    if n.given:
        d["given"] = n.given
    return d


def _name_from_csl(d: dict) -> Name:
    if d.get("literal"):
        return Name(literal=d["literal"])
    return Name(family=d.get("family", ""), given=d.get("given", ""))


def to_csl(item: Reference | OnlineRecord, key: str | None = None) -> dict:
    if isinstance(item, Reference):
        return _ref_to_csl(item, key)
    return _record_to_csl(item, key)


def _ref_to_csl(ref: Reference, key: str | None) -> dict:
    out: dict = {"id": key or ref.key, "type": ref.type}
    if ref.title:
        out["title"] = ref.title
    if ref.authors:
        out["author"] = [_name_to_csl(n) for n in ref.authors]
    extra = dict(ref.extra)
    month = _parse_month(extra.get("month"))
    if month is not None:
        extra.pop("month")
    if ref.year is not None:
        parts = [ref.year, month] if month is not None else [ref.year]
        out["issued"] = {"date-parts": [parts]}
    if ref.journal:
        out["container-title"] = ref.journal
    if ref.volume:
        out["volume"] = ref.volume
    if ref.number:
        out["issue"] = ref.number
    if ref.pages:
        out["page"] = ref.pages
    if ref.doi:
        out["DOI"] = ref.doi
    if ref.url:
        out["URL"] = ref.url
    if "editor" in extra:
        editors = split_authors(extra.pop("editor"))
        if editors:
            out["editor"] = [_name_to_csl(n) for n in editors]
    if "publisher" in extra:
        out["publisher"] = extra.pop("publisher")
    else:
        for alias in ("school", "institution"):
            if alias in extra:
                out["publisher"] = extra.pop(alias)
                break
    for bib_field, csl_var in _EXTRA_TO_CSL.items():
        if bib_field in extra:
            out[csl_var] = extra.pop(bib_field)
    if extra:
        out["custom"] = extra
    return out


def _record_to_csl(rec: OnlineRecord, key: str | None) -> dict:
    out: dict = {
        "id": key or rec.doi or rec.ids.get(rec.source) or rec.title[:60],
        "type": rec.type or "document",
        "title": rec.title,
    }
    if rec.authors:
        out["author"] = [_name_to_csl(n) for n in rec.authors]
    if rec.year is not None:
        out["issued"] = {"date-parts": [[rec.year]]}
    if rec.journal:
        out["container-title"] = rec.journal
    if rec.volume:
        out["volume"] = rec.volume
    if rec.number:
        out["issue"] = rec.number
    if rec.pages:
        out["page"] = rec.pages
    if rec.doi:
        out["DOI"] = rec.doi
    if rec.url:
        out["URL"] = rec.url
    if rec.abstract:
        out["abstract"] = rec.abstract
    if rec.publisher:
        out["publisher"] = rec.publisher
    out["custom"] = {"source": rec.source, **rec.ids}
    return out


def from_csl(item: dict) -> Reference:
    csl_type = str(item.get("type", "document"))
    extra: dict[str, str] = {}
    year = None
    date_parts = (item.get("issued") or {}).get("date-parts") or [[]]
    if date_parts[0]:
        first = date_parts[0]
        if first and first[0]:
            year = int(first[0])
        if len(first) > 1 and first[1]:
            extra["month"] = str(first[1])
    if item.get("editor"):
        editors = [_name_from_csl(e) for e in item["editor"]]
        extra["editor"] = " and ".join(str(e) for e in editors)
    if item.get("publisher"):
        alias = {"thesis": "school", "report": "institution"}.get(csl_type, "publisher")
        extra[alias] = str(item["publisher"])
    for csl_var, bib_field in _CSL_TO_EXTRA.items():
        if item.get(csl_var):
            extra[bib_field] = str(item[csl_var])
    for k, v in (item.get("custom") or {}).items():
        if isinstance(v, str):
            extra.setdefault(k, v)
    container = item.get("container-title")
    if isinstance(container, list):
        container = container[0] if container else None
    return Reference(
        key=str(item.get("id", "")),
        title=str(item.get("title", "")),
        authors=[_name_from_csl(a) for a in item.get("author", [])],
        type=csl_type,
        year=year,
        journal=str(container) if container else None,
        volume=str(item["volume"]) if item.get("volume") else None,
        number=str(item["issue"]) if item.get("issue") else None,
        pages=str(item["page"]) if item.get("page") else None,
        doi=item.get("DOI"),
        url=item.get("URL"),
        extra=extra,
    )
