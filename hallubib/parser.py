"""Parse .bib and .tex files to extract references."""

import re
import unicodedata
from pathlib import Path

from .types import EntryKind, Reference

LATEX_ACCENT_MAP: dict[str, str] = {
    "`": "\u0300", "'": "\u0301", "^": "\u0302", "~": "\u0303",
    "=": "\u0304", "u": "\u0306", ".": "\u0307", '"': "\u0308",
    "r": "\u030A", "H": "\u030B", "v": "\u030C", "d": "\u0323",
    "c": "\u0327", "k": "\u0328",
}

_ENTRY_KIND_MAP: dict[str, EntryKind] = {
    "article": EntryKind.ARTICLE,
    "book": EntryKind.BOOK,
    "inproceedings": EntryKind.INPROCEEDINGS,
    "conference": EntryKind.INPROCEEDINGS,
    "incollection": EntryKind.INCOLLECTION,
}

_BIB_ENTRY_RE = re.compile(
    r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE
)
_BIB_FIELD_RE = re.compile(
    r"(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|\"([^\"]*)\")",
    re.DOTALL,
)
_BIBITEM_RE = re.compile(
    r"\\bibitem\{([^}]+)\}\s*(.*?)(?=\\bibitem\{|\\end\{thebibliography\})",
    re.DOTALL,
)
_URL_RE = re.compile(r"\\url\{([^}]+)\}")
_DOI_RE = re.compile(r"(?:doi\.org/|doi\s*=\s*\{?)(10\.\d{4,}/[^\s},]+)", re.IGNORECASE)
_YEAR_PAREN_RE = re.compile(r"\((\d{4})\)")
_YEAR_BARE_RE = re.compile(r"\b(\d{4})\b")


def latex_to_unicode(s: str) -> str:
    s = re.sub(r"\\t\{(\w)(\w)\}", r"\1\2", s)
    s = re.sub(r"\{\\(\w)\}", r"\1", s)

    def _replace_accent(m: re.Match[str]) -> str:
        cmd = m.group(1)
        char = m.group(2) or m.group(3) or ""
        if cmd in LATEX_ACCENT_MAP and char:
            combined = char + LATEX_ACCENT_MAP[cmd]
            return unicodedata.normalize("NFC", combined)
        return char

    s = re.sub(r"\\([`'^\"~=.cuvkrHd])\{(\w)\}", _replace_accent, s)
    s = re.sub(r"\\([`'^\"~=.cuvkrHd])\s?(\w)", _replace_accent, s)
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"\\&", "&", s)
    s = re.sub(r"~", " ", s)
    return s.strip()


def normalize_author(name: str) -> str:
    name = latex_to_unicode(name.strip())
    name = re.sub(r"\s+", " ", name)
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        return f"{parts[0]}, {parts[1]}" if len(parts) == 2 else name
    words = name.split()
    if len(words) >= 2:
        return f"{words[-1]}, {' '.join(words[:-1])}"
    return name


def split_authors(raw: str) -> list[str]:
    raw = latex_to_unicode(raw)
    if " and " in raw.lower():
        parts = re.split(r"\s+and\s+", raw, flags=re.IGNORECASE)
    else:
        parts = [raw]
    authors = []
    for p in parts:
        p = p.strip()
        if not p or p.lower() == "others":
            continue
        authors.append(normalize_author(p))
    return authors


def _extract_bib_field(fields: dict[str, str], name: str) -> str | None:
    val = fields.get(name)
    if val is None:
        return None
    val = latex_to_unicode(val).strip()
    return val if val else None


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
        kind = _ENTRY_KIND_MAP.get(entry_type, EntryKind.MISC)

        start = entry_match.end()
        depth = 1
        pos = start
        while pos < len(text) and depth > 0:
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
            pos += 1
        body = text[start:pos - 1] if depth == 0 else text[start:]

        fields: dict[str, str] = {}
        for fm in _BIB_FIELD_RE.finditer(body):
            fname = fm.group(1).lower()
            fval = fm.group(2) if fm.group(2) is not None else fm.group(3)
            fields[fname] = fval

        title = _extract_bib_field(fields, "title") or ""
        authors = split_authors(fields.get("author", ""))
        year = _parse_year(fields.get("year"))
        journal = _extract_bib_field(fields, "journal") or _extract_bib_field(fields, "booktitle")
        doi_raw = fields.get("doi")
        doi = latex_to_unicode(doi_raw).strip() if doi_raw else None
        url = _extract_bib_field(fields, "url")

        refs.append(Reference(
            key=key,
            entry_kind=kind,
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            volume=_extract_bib_field(fields, "volume"),
            number=_extract_bib_field(fields, "number"),
            pages=_extract_bib_field(fields, "pages"),
            doi=doi,
            url=url,
            raw=body.strip(),
        ))
    return refs


def parse_tex(text: str) -> list[Reference]:
    refs: list[Reference] = []
    for m in _BIBITEM_RE.finditer(text):
        key = m.group(1)
        raw_body = m.group(2).strip()
        clean = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", raw_body)
        clean = re.sub(r"[{}\\]", "", clean)
        clean = re.sub(r"\s+", " ", clean).strip()

        url_m = _URL_RE.search(raw_body)
        url = url_m.group(1) if url_m else None
        doi_m = _DOI_RE.search(raw_body)
        doi = doi_m.group(1) if doi_m else None

        year_m = _YEAR_PAREN_RE.search(clean)
        if not year_m:
            year_m = _YEAR_BARE_RE.search(clean)
        year = int(year_m.group(1)) if year_m else None

        title = ""
        authors_raw: list[str] = []
        if year_m:
            before_year = clean[:year_m.start()].strip().rstrip(",. ")
            after_year = clean[year_m.end():].strip().lstrip(".) ")
            if before_year:
                parts = re.split(r"\.\s+", before_year, maxsplit=1)
                if len(parts) >= 1:
                    authors_raw = [normalize_author(a.strip()) for a in
                                   re.split(r",\s*(?:&|and)\s*|,\s+", parts[0])
                                   if a.strip() and not a.strip().startswith("...")]
            if after_year:
                sentences = re.split(r"\.\s+", after_year, maxsplit=1)
                title = sentences[0].strip().rstrip(".")
                journal_part = sentences[1].strip() if len(sentences) > 1 else None
            else:
                title = before_year
                journal_part = None
        else:
            title = clean[:80]
            journal_part = None

        journal = None
        volume = None
        pages = None
        if journal_part:
            vol_m = re.search(r"(\d+)\s*\(", journal_part)
            if vol_m:
                journal = journal_part[:vol_m.start()].strip().rstrip(",")
                volume = vol_m.group(1)
            pages_m = re.search(r"(\d+[-–]\d+)", journal_part)
            if pages_m:
                pages = pages_m.group(1)

        refs.append(Reference(
            key=key,
            entry_kind=EntryKind.MISC,
            title=title,
            authors=authors_raw,
            year=year,
            journal=journal,
            volume=volume,
            pages=pages,
            doi=doi,
            url=url,
            raw=raw_body,
        ))
    return refs


def parse_file(path: Path) -> list[Reference]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".bib":
        return parse_bib(text)
    if path.suffix == ".tex":
        return parse_tex(text)
    raise ValueError(f"Unsupported file type: {path.suffix}")
