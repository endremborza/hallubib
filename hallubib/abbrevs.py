"""Journal abbreviation database loaded from csv.gz."""

import csv
import gzip
import re
import unicodedata
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"
_ABBREV_FILE = _DATA_DIR / "journal_abbrevs.csv.gz"

_full_to_abbrev: dict[str, str] = {}
_abbrev_to_full: dict[str, str] = {}
_loaded = False


def _norm_key(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9\s]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    if not _ABBREV_FILE.exists():
        return
    with gzip.open(_ABBREV_FILE, "rt", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            full, abbrev = row[0].strip(), row[1].strip()
            if not full or not abbrev:
                continue
            fk = _norm_key(full)
            ak = _norm_key(abbrev)
            if fk and ak and fk != ak:
                _full_to_abbrev[fk] = fk
                _abbrev_to_full[ak] = fk


def expand(name: str) -> str:
    _load()
    nk = _norm_key(name)
    full = _abbrev_to_full.get(nk)
    if full:
        return full
    if nk in _full_to_abbrev:
        return nk
    return nk


def known_count() -> int:
    _load()
    return len(_full_to_abbrev)
