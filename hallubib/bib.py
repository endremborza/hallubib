"""Serialize CSL-JSON items back to BibTeX text."""

from collections.abc import Iterable

from .csl import CSL_TYPE_TO_BIB

_MONTH_MACROS = "jan feb mar apr may jun jul aug sep oct nov dec".split()

_FIELD_ORDER = [
    "author",
    "editor",
    "title",
    "journal",
    "booktitle",
    "year",
    "month",
    "volume",
    "number",
    "pages",
    "publisher",
    "school",
    "institution",
    "address",
    "edition",
    "series",
    "chapter",
    "isbn",
    "issn",
    "doi",
    "url",
    "note",
    "abstract",
    "keywords",
    "language",
]

_CSL_VAR_TO_BIB = {
    "publisher-place": "address",
    "edition": "edition",
    "collection-title": "series",
    "chapter-number": "chapter",
    "ISBN": "isbn",
    "ISSN": "issn",
    "note": "note",
    "abstract": "abstract",
    "keyword": "keywords",
    "language": "language",
}


def _brace(value: str) -> str:
    """Wrap a field value in braces, neutralizing anything that would unbalance it.

    Values arrive from online records and hand-written .bib files. A stray `}`
    there closes the entry early and corrupts everything after it on reparse, so
    unmatched braces are escaped — matched ones (`{\\LaTeX}`, protected capitals)
    are left exactly as the source wrote them.
    """
    return "{%s}" % _escape_unmatched(value)


def _escape_unmatched(value: str) -> str:
    opened: list[int] = []
    unmatched: set[int] = set()
    for i, char in enumerate(value):
        if char == "{":
            opened.append(i)
        elif char == "}":
            if opened:
                opened.pop()
            else:
                unmatched.add(i)
    unmatched.update(opened)
    escaped = "".join(
        "\\" + char if i in unmatched else char for i, char in enumerate(value)
    )
    trailing = len(escaped) - len(escaped.rstrip("\\"))
    return escaped + "\\" if trailing % 2 else escaped


def _bib_name(n: dict) -> str:
    if n.get("literal"):
        return _brace(n["literal"])
    family = n.get("family", "")
    given = n.get("given", "")
    return f"{family}, {given}" if given else family


def _bib_type(item: dict) -> str:
    csl_type = str(item.get("type", "document"))
    btype = CSL_TYPE_TO_BIB.get(csl_type, "misc")
    if btype == "phdthesis" and "master" in str(item.get("genre", "")).lower():
        return "mastersthesis"
    return btype


def entry_to_bib(item: dict) -> str:
    btype = _bib_type(item)
    fields: dict[str, str] = {}
    if item.get("author"):
        fields["author"] = " and ".join(_bib_name(n) for n in item["author"])
    if item.get("editor"):
        fields["editor"] = " and ".join(_bib_name(n) for n in item["editor"])
    if item.get("title"):
        fields["title"] = str(item["title"])
    if item.get("container-title"):
        container_field = (
            "booktitle" if btype in ("inproceedings", "incollection") else "journal"
        )
        fields[container_field] = str(item["container-title"])
    date_parts = (item.get("issued") or {}).get("date-parts") or [[]]
    if date_parts[0]:
        first = date_parts[0]
        if first and first[0]:
            fields["year"] = str(first[0])
        if len(first) > 1 and first[1] and 1 <= int(first[1]) <= 12:
            fields["month"] = _MONTH_MACROS[int(first[1]) - 1]
    if item.get("volume"):
        fields["volume"] = str(item["volume"])
    if item.get("issue"):
        fields["number"] = str(item["issue"])
    if item.get("page"):
        fields["pages"] = str(item["page"])
    if item.get("publisher"):
        alias = {
            "phdthesis": "school",
            "mastersthesis": "school",
            "techreport": "institution",
        }.get(btype, "publisher")
        fields[alias] = str(item["publisher"])
    for csl_var, bib_field in _CSL_VAR_TO_BIB.items():
        if item.get(csl_var):
            fields.setdefault(bib_field, str(item[csl_var]))
    if item.get("DOI"):
        fields["doi"] = str(item["DOI"])
    if item.get("URL"):
        fields["url"] = str(item["URL"])
    for k, v in (item.get("custom") or {}).items():
        if isinstance(v, str):
            fields.setdefault(k, v)

    ordered = [f for f in _FIELD_ORDER if f in fields]
    ordered += [f for f in fields if f not in _FIELD_ORDER]
    lines = ["@%s{%s," % (btype, item.get("id", ""))]
    for f in ordered:
        value = fields[f] if f == "month" else _brace(fields[f])
        lines.append(f"  {f} = {value},")
    lines.append("}")
    return "\n".join(lines)


def to_bib(items: Iterable[dict]) -> str:
    return "\n\n".join(entry_to_bib(i) for i in items) + "\n"
