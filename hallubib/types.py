from dataclasses import dataclass, field
from enum import Enum, auto


class EntryKind(Enum):
    ARTICLE = auto()
    BOOK = auto()
    INPROCEEDINGS = auto()
    INCOLLECTION = auto()
    MISC = auto()


class Status(Enum):
    VERIFIED = "Verified"
    AUTO_CORRECTABLE = "Auto-correctable"
    NEEDS_ATTENTION = "Needs attention"
    UNKNOWN = "Unknown"


@dataclass(frozen=True, slots=True)
class Reference:
    key: str
    entry_kind: EntryKind
    title: str
    authors: list[str]
    year: int | None = None
    journal: str | None = None
    volume: str | None = None
    number: str | None = None
    pages: str | None = None
    doi: str | None = None
    url: str | None = None
    raw: str = ""


@dataclass(frozen=True, slots=True)
class OnlineRecord:
    source: str
    title: str
    authors: list[str]
    year: int | None = None
    journal: str | None = None
    volume: str | None = None
    number: str | None = None
    pages: str | None = None
    doi: str | None = None


@dataclass(slots=True)
class FieldDiff:
    field_name: str
    local_value: str | None
    online_value: str | None


@dataclass(slots=True)
class CheckResult:
    reference: Reference
    status: Status
    best_match: OnlineRecord | None = None
    diffs: list[FieldDiff] = field(default_factory=list)
    suggestions: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
