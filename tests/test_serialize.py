import json

from hallubib import __version__
from hallubib.serialize import results_to_dict
from hallubib.types import (
    CheckResult,
    MatchEvidence,
    Name,
    OnlineRecord,
    Reference,
    SourceAttempt,
    Status,
)


def _result() -> CheckResult:
    ref = Reference(
        key="k",
        title="T",
        authors=[Name(family="Gale", given="David")],
        type="article-journal",
        year=2020,
    )
    return CheckResult(
        reference=ref,
        status=Status.VERIFIED,
        best_match=OnlineRecord(
            source="openalex",
            title="T",
            authors=[Name(family="Gale", given="David")],
            ids={"openalex": "W1"},
        ),
        score=0.97,
        evidence=MatchEvidence(1.0, 1.0, True, True, 1.0),
        attempts=[SourceAttempt("openalex", "title:T", ok=True, hits=1)],
    )


def test_json_round_trip():
    data = results_to_dict([_result()])
    assert data["hallubib_version"] == __version__
    dumped = json.dumps(data, ensure_ascii=False)
    loaded = json.loads(dumped)
    r = loaded["results"][0]
    assert r["status"] == "Verified"
    assert r["reference"]["authors"][0]["family"] == "Gale"
    assert r["best_match"]["ids"]["openalex"] == "W1"
    assert r["attempts"][0]["ok"] is True
    assert r["evidence"]["title_sim"] == 1.0


def test_deterministic():
    a = json.dumps(results_to_dict([_result()]))
    b = json.dumps(results_to_dict([_result()]))
    assert a == b
