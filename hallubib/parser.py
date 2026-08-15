"""Parse .bib and .tex bibliography text into References."""

import re
from pathlib import Path

from .csl import BIB_TYPE_TO_CSL
from .names import latex_to_unicode, parse_name, split_authors
from .types import Name, Reference

_BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)
_BIB_FIELD_RE = re.compile(
    r"([\w-]+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|\"([^\"]*)\"|([^\s,{}\"]+))",
    re.DOTALL,
)
_BIBITEM_RE = re.compile(
    r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}\s*"
    r"(.*?)(?=\\bibitem\b|\\end\{thebibliography\}|\Z)",
    re.DOTALL,
)
_URL_RE = re.compile(r"\\url\{([^}]+)\}")
_DOI_RE = re.compile(r"(?:doi\.org/|doi\s*=\s*\{?)(10\.\d{4,}/[^\s},]+)", re.IGNORECASE)
_YEAR_PAREN_RE = re.compile(r"\(((?:1[5-9]|20)\d{2})[a-z]?\)")
_YEAR_RE = re.compile(r"\b((?:1[5-9]|20)\d{2})\b")
_SENTENCE_SPLIT_RE = re.compile(r"(?<![A-Z])(?<!et al)\.\s+")
_QUOTED_TITLE_RE = re.compile(r"(?:``(.+?)''|[“\"](.+?)[”\"])")
_INITIALS_RE = re.compile(r"^(?:[A-Z]\.?[\s-]*)+$")

_FIRST_CLASS_FIELDS = frozenset(
    {
        "title",
        "author",
        "year",
        "journal",
        "booktitle",
        "volume",
        "number",
        "pages",
        "doi",
        "url",
    }
)
_NON_JOURNAL_VENUES = ("retrieved", "accessed", "available", "version", "in press")


def _parse_year(val: str | None) -> int | None:
    if val is None:
        return None
    m = re.search(r"\d{4}", val)
    return int(m.group()) if m else None


def parse_bib(text: str) -> list[Reference]:
    refs: list[Reference] = []
    for entry_match in _BIB_ENTRY_RE.finditer(text):
        entry_type = entry_match.group(1).lower()
        key = entry_match.group(2)

        start = entry_match.end()
        depth = 1
        pos = start
        while pos < len(text) and depth > 0:
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
            pos += 1
        body = text[start : pos - 1] if depth == 0 else text[start:]

        fields: dict[str, str] = {}
        for fm in _BIB_FIELD_RE.finditer(body):
            fname = fm.group(1).lower()
            fval = next(g for g in fm.groups()[1:] if g is not None)
            fields[fname] = fval

        def norm(name: str) -> str | None:
            val = fields.get(name)
            if val is None:
                return None
            val = latex_to_unicode(val).strip()
            return val if val else None

        year = _parse_year(fields.get("year"))
        journal = norm("journal")
        extra: dict[str, str] = {}
        if "booktitle" in fields:
            booktitle = norm("booktitle")
            if journal is None:
                journal = booktitle
            elif booktitle:
                extra["booktitle"] = booktitle
        if year is None and fields.get("year"):
            extra["year"] = latex_to_unicode(fields["year"]).strip()
        for fname, fval in fields.items():
            if fname in _FIRST_CLASS_FIELDS:
                continue
            clean = latex_to_unicode(fval).strip()
            if clean:
                extra[fname] = clean

        doi_raw = fields.get("doi")
        refs.append(
            Reference(
                key=key,
                title=norm("title") or "",
                authors=split_authors(fields.get("author", "")),
                type=BIB_TYPE_TO_CSL.get(entry_type, "document"),
                year=year,
                journal=journal,
                volume=norm("volume"),
                number=norm("number"),
                pages=norm("pages"),
                doi=latex_to_unicode(doi_raw).strip() if doi_raw else None,
                url=norm("url"),
                extra=extra,
                raw=body.strip(),
            )
        )
    return refs


def _clean_tex(s: str) -> str:
    s = _URL_RE.sub(" ", s)
    s = re.sub(r"\\(?:newblock|em|it|bf|sc|tt|sl)\b", " ", s)
    for _ in range(2):
        s = re.sub(r"\\[a-zA-Z]+\*?\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"[{}\\]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_free_authors(s: str) -> list[Name]:
    s = re.sub(r"\bet\s+al\.?", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"\s+", " ", s).strip().strip(".,;: ")
    if not s:
        return []
    names: list[Name] = []
    for seg in re.split(r"\s+and\s+", s, flags=re.IGNORECASE):
        tokens = [t.strip() for t in seg.split(",")]
        tokens = [
            t
            for t in tokens
            if t and "..." not in t and "…" not in t and not any(c.isdigit() for c in t)
        ]
        if not tokens or seg.strip().lower() == "others":
            continue
        if len(tokens) == 2 and not _INITIALS_RE.match(tokens[0]):
            names.append(Name(family=tokens[0], given=tokens[1]))
            continue
        i = 0
        while i < len(tokens):
            if i + 1 < len(tokens) and _INITIALS_RE.match(tokens[i + 1]):
                names.append(Name(family=tokens[i], given=tokens[i + 1]))
                i += 2
            else:
                names.append(parse_name(tokens[i]))
                i += 1
    return names


def _parse_venue(venue: str) -> tuple[str | None, str | None, str | None, str | None]:
    venue = venue.strip().strip(".,; ")
    if not venue:
        return None, None, None, None
    journal = volume = number = pages = None
    vol_m = re.search(r"(\d+)\s*\((\d+(?:[-–—]\d+)?)\)", venue)
    if vol_m:
        journal = venue[: vol_m.start()].strip(" ,.") or None
        volume, number = vol_m.group(1), vol_m.group(2)
    else:
        vol_m = re.search(r",\s*(\d+)\s*[:,]", venue)
        if vol_m:
            journal = venue[: vol_m.start()].strip(" ,.") or None
            volume = vol_m.group(1)
    pages_m = re.search(r"(\d+)\s*(?:--|[-–—])\s*(\d+)", venue)
    if pages_m and _YEAR_RE.fullmatch(pages_m.group(0)) is None:
        pages = f"{pages_m.group(1)}-{pages_m.group(2)}"
    if journal is None:
        head = venue.split(",")[0].strip(" .")
        if head and not head[0].isdigit():
            if not head.lower().startswith(_NON_JOURNAL_VENUES):
                journal = head
    return journal, volume, number, pages


def _split_title_venue(rest: str) -> tuple[str, str]:
    qm = _QUOTED_TITLE_RE.search(rest)
    if qm:
        title = (qm.group(1) or qm.group(2)).strip().strip(",. ")
        return title, rest[qm.end() :].strip()
    parts = _SENTENCE_SPLIT_RE.split(rest, maxsplit=1)
    title = parts[0].strip().rstrip(".")
    venue = parts[1].strip() if len(parts) > 1 else ""
    return title, venue


def parse_bibitem(key: str, raw_text: str) -> Reference:
    url_m = _URL_RE.search(raw_text)
    url = url_m.group(1).strip() if url_m else None
    doi_m = _DOI_RE.search(raw_text)
    doi = doi_m.group(1) if doi_m else None

    if "\\newblock" in raw_text:
        blocks = [b for b in map(_clean_tex, raw_text.split("\\newblock")) if b]
    else:
        blocks = []

    if len(blocks) >= 2:
        authors = _parse_free_authors(blocks[0])
        title, quoted_venue = _split_title_venue(blocks[1])
        venue = " ".join([quoted_venue, *blocks[2:]]).strip()
        search_space = " ".join(blocks)
    else:
        clean = _clean_tex(raw_text)
        search_space = clean
        paren = _YEAR_PAREN_RE.search(clean)
        if paren:
            authors = _parse_free_authors(clean[: paren.start()])
            rest = clean[paren.end() :].lstrip(".) ")
            title, venue = _split_title_venue(rest)
        else:
            parts = _SENTENCE_SPLIT_RE.split(clean, maxsplit=2)
            if len(parts) >= 2:
                authors = _parse_free_authors(parts[0])
                title = parts[1].strip().rstrip(".")
                venue = parts[2] if len(parts) > 2 else ""
            else:
                authors = []
                title = clean[:120].strip().rstrip(".")
                venue = ""

    paren = _YEAR_PAREN_RE.search(search_space)
    if paren:
        year = int(paren.group(1))
    else:
        bare_years = _YEAR_RE.findall(search_space)
        year = int(bare_years[-1]) if bare_years else None

    journal, volume, number, pages = _parse_venue(venue)
    return Reference(
        key=key,
        title=title,
        authors=authors,
        type="document",
        year=year,
        journal=journal,
        volume=volume,
        number=number,
        pages=pages,
        doi=doi,
        url=url,
        raw=raw_text.strip(),
    )


def parse_tex(text: str) -> list[Reference]:
    return [
        parse_bibitem(m.group(1), m.group(2).strip())
        for m in _BIBITEM_RE.finditer(text)
    ]


def parse_file(path: Path) -> list[Reference]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".bib":
        return parse_bib(text)
    if path.suffix == ".tex":
        return parse_tex(text)
    raise ValueError(f"Unsupported file type: {path.suffix}")
