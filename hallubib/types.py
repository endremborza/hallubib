from dataclasses import dataclass, field
from enum import StrEnum


class Status(StrEnum):
    UNKNOWN = "Unknown"
    NEEDS_ATTENTION = "Needs attention"
    AUTO_CORRECTABLE = "Auto-correctable"
    URL_REFERENCE = "URL reference"
    VERIFIED = "Verified"


class DiffKind(StrEnum):
    CORRECTION = "correction"
    SUPPLEMENT = "supplement"


@dataclass(frozen=True, slots=True)
class Name:
    family: str = ""
    given: str = ""
    literal: str = ""

    def __str__(self) -> str:
        if self.literal:
            return self.literal
        if self.given:
            return f"{self.family}, {self.given}"
        return self.family


@dataclass(frozen=True, slots=True)
class Reference:
    key: str
    title: str
    authors: list[Name]
    type: str = "document"
    year: int | None = None
    journal: str | None = None
    volume: str | None = None
    number: str | None = None
    pages: str | None = None
    doi: str | None = None
    url: str | None = None
    extra: dict[str, str] = field(default_factory=dict)
    raw: str = ""


@dataclass(frozen=True, slots=True)
class OnlineRecord:
    source: str
    title: str
    authors: list[Name]
    year: int | None = None
    journal: str | None = None
    volume: str | None = None
    number: str | None = None
    pages: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    type: str | None = None
    publisher: str | None = None
    ids: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceAttempt:
    source: str
    query: str
    ok: bool
    hits: int = 0
    error: str | None = None


@dataclass(frozen=True, slots=True)
class MatchEvidence:
    title_sim: float
    author_overlap: float
    first_author_match: bool
    year_ok: bool
    journal_sim: float


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
