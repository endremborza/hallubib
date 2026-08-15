from dataclasses import dataclass, field
from enum import Enum, auto


class EntryKind(Enum):
    ARTICLE = auto()
    BOOK = auto()
    INPROCEEDINGS = auto()
    INCOLLECTION = auto()
    MISC = auto()


class Status(Enum):
    UNKNOWN = "Unknown"
    NEEDS_ATTENTION = "Needs attention"
    AUTO_CORRECTABLE = "Auto-correctable"
    URL_REFERENCE = "URL reference"
    VERIFIED = "Verified"


class DiffKind(Enum):
    CORRECTION = "correction"
    SUPPLEMENT = "supplement"


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
    kind: DiffKind = DiffKind.CORRECTION


@dataclass(slots=True)
class CheckResult:
    reference: Reference
    status: Status
    best_match: OnlineRecord | None = None
    score: float = 0.0
    evidence: MatchEvidence | None = None
    diffs: list[FieldDiff] = field(default_factory=list)
    suggestions: dict[str, str] = field(default_factory=dict)
    alternatives: list[OnlineRecord] = field(default_factory=list)
    attempts: list[SourceAttempt] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
