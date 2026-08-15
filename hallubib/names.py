"""Structured personal-name parsing and LaTeX text normalization."""

import re
import unicodedata

from .types import Name

LATEX_ACCENT_MAP: dict[str, str] = {
    "`": "\u0300",
    "'": "\u0301",
    "^": "\u0302",
    "~": "\u0303",
    "=": "\u0304",
    "u": "\u0306",
    ".": "\u0307",
    '"': "\u0308",
    "r": "\u030a",
    "H": "\u030b",
    "v": "\u030c",
    "d": "\u0323",
    "c": "\u0327",
    "k": "\u0328",
}

_PARTICLES = frozenset(
    "van von der den de la le del della di da do dos das du ter ten zu zur vom".split()
)
_SUFFIXES = frozenset({"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"})


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


def parse_name(s: str) -> Name:
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return Name()
    if "," in s:
        parts = [p.strip() for p in s.split(",")]
        family = parts[0]
        rest = [p for p in parts[1:] if p]
        if len(rest) >= 2 and rest[0].lower() in _SUFFIXES:
            given = " ".join([*rest[1:], rest[0]])
        else:
            given = " ".join(rest)
        return Name(family=family, given=given)
    tokens = s.split()
    suffix = ""
    if len(tokens) >= 3 and tokens[-1].lower() in _SUFFIXES:
        suffix = tokens[-1]
        tokens = tokens[:-1]
    if len(tokens) == 1:
        return Name(family=tokens[0], given=suffix)
    fam_start = len(tokens) - 1
    while fam_start > 0 and tokens[fam_start - 1].lower() in _PARTICLES:
        fam_start -= 1
    family = " ".join(tokens[fam_start:])
    given = " ".join([*tokens[:fam_start], suffix]).strip()
    return Name(family=family, given=given)


def _split_top_level_and(raw: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    lower = raw.lower()
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        if depth == 0 and lower.startswith(" and ", i):
            parts.append("".join(buf))
            buf = []
            i += 5
            continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts


def _is_brace_wrapped(s: str) -> bool:
    if len(s) < 2 or s[0] != "{" or s[-1] != "}":
        return False
    depth = 0
    for i, c in enumerate(s):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i == len(s) - 1
    return False


def split_authors(raw: str) -> list[Name]:
    names: list[Name] = []
    for part in _split_top_level_and(raw):
        part = part.strip()
        if not part or part.lower() == "others":
            continue
        if _is_brace_wrapped(part):
            literal = latex_to_unicode(part[1:-1])
            if literal:
                names.append(Name(literal=literal))
            continue
        clean = latex_to_unicode(part)
        if not clean or clean.lower() == "others":
            continue
        names.append(parse_name(clean))
    return names
