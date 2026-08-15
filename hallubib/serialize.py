"""Turn check results into a stable, versioned, JSON-ready structure."""

from collections.abc import Iterable
from dataclasses import asdict

from .types import CheckResult


def result_to_dict(result: CheckResult) -> dict:
    return asdict(result)


def results_to_dict(results: Iterable[CheckResult]) -> dict:
    from hallubib import __version__

    return {
        "hallubib_version": __version__,
        "results": [asdict(r) for r in results],
    }
