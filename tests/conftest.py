from dataclasses import asdict
from pathlib import Path

import pytest
from requests.adapters import HTTPAdapter

from hallubib import config

from . import cassettes

_SOURCE_MODULES = ("arxiv", "crossref", "doi", "openalex", "semanticscholar")

GOLDEN_BIB = Path(__file__).parent / "fixtures" / "golden.bib"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="run the drift canary against the live source APIs",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]):
    if config.getoption("--run-network"):
        return
    skip = pytest.mark.skip(reason="needs --run-network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Keep global config mutations and cache writes inside the test's tmp_path."""
    saved = asdict(config.get_config())
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    yield
    config.configure(**saved)


@pytest.fixture(autouse=True)
def no_egress(request, monkeypatch):
    """Everything outside the drift canary is offline, and provably so: a test
    that reaches the network gets an error naming the URL, not a slow pass."""
    if "network" in request.keywords:
        return

    def forbidden(self, req, *args, **kwargs):
        raise AssertionError(
            f"test attempted a real request to {req.url}\n"
            "use the `cassette` fixture, or mark the test `network`"
        )

    monkeypatch.setattr(HTTPAdapter, "send", forbidden)


@pytest.fixture
def cassette(monkeypatch, tmp_path):
    """Serve the recorded golden.bib interactions in place of the network.

    Patching lands on `request` rather than the session, so each source client
    still runs its own cache lookup, status handling, parsing and cache write.
    Returns the player, which carries `.calls` and `.interactions`.
    """
    interactions = cassettes.load(cassettes.CASSETTE_DIR / "golden.json")
    player = cassettes.player(interactions)
    monkeypatch.setattr("hallubib.sources._http.request", player)
    for module in _SOURCE_MODULES:
        monkeypatch.setattr(f"hallubib.sources.{module}.request", player)
    monkeypatch.setattr(
        "hallubib.verify.validate_url", cassettes.url_checker(interactions)
    )
    config.configure(cache_dir=tmp_path / "cassette-cache")
    return player
