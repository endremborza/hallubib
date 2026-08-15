"""Text and name similarity used for matching references to online records."""

import re
import unicodedata
from difflib import SequenceMatcher

from .abbrevs import expand as expand_journal
from .types import Name


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def norm_text(s: str) -> str:
    s = strip_accents(s.lower())
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, norm_text(a), norm_text(b)).ratio()


def author_last(name: Name) -> str:
    if name.family:
        return norm_text(name.family)
    if name.literal:
        parts = name.literal.split()
        return norm_text(parts[-1]) if parts else ""
    return ""


def first_author_match(ref_authors: list[Name], online_authors: list[Name]) -> bool:
    if not ref_authors or not online_authors:
        return not ref_authors and not online_authors
    return author_last(ref_authors[0]) == author_last(online_authors[0])


def author_overlap(ref_authors: list[Name], online_authors: list[Name]) -> float:
    if not ref_authors or not online_authors:
        return 1.0 if not ref_authors and not online_authors else 0.0
    ref_lasts = {author_last(a) for a in ref_authors} - {""}
    online_lasts = {author_last(a) for a in online_authors} - {""}
    if not ref_lasts or not online_lasts:
        return 0.0
    intersection = ref_lasts & online_lasts
    return len(intersection) / min(len(ref_lasts), len(online_lasts))


def _norm_journal(j: str | None) -> str:
    if not j:
        return ""
    return expand_journal(j)


def journal_similarity(a: str | None, b: str | None) -> float:
    na, nb = _norm_journal(a), _norm_journal(b)
    if not na or not nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()
