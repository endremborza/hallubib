"""Check bibliography for hallucinations"""

__version__ = "0.2.0"

from .bib import entry_to_bib, to_bib
from .config import Config, configure, get_config
from .csl import from_csl, to_csl
from .parser import parse_bib, parse_bibitem, parse_file, parse_tex
from .serialize import result_to_dict, results_to_dict
from .sources import SourceError
from .types import (
    CheckResult,
    DiffKind,
    FieldDiff,
    MatchEvidence,
    Name,
    OnlineRecord,
    Reference,
    SourceAttempt,
    Status,
)
from .verify import (
    categorize,
    check_reference,
    check_references,
    check_references_iter,
)

__all__ = [
    "CheckResult",
    "Config",
    "DiffKind",
    "FieldDiff",
    "MatchEvidence",
    "Name",
    "OnlineRecord",
    "Reference",
    "SourceAttempt",
    "SourceError",
    "Status",
    "__version__",
    "categorize",
    "check_reference",
    "check_references",
    "check_references_iter",
    "configure",
    "entry_to_bib",
    "from_csl",
    "get_config",
    "parse_bib",
    "parse_bibitem",
    "parse_file",
    "parse_tex",
    "result_to_dict",
    "results_to_dict",
    "to_bib",
    "to_csl",
]
