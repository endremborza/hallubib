import json
from pathlib import Path

import pytest

from hallubib import cache, config
from hallubib.cli import main
from hallubib.types import (
    CheckResult,
    DiffKind,
    FieldDiff,
    Name,
    OnlineRecord,
    Reference,
    Status,
)

_BIB = """@article{gs62,
  title = {College Admissions and the Stability of Marriage},
  author = {Gale, David and Shapley, Lloyd S.},
  journal = {The American Mathematical Monthly},
  year = {1962},
  volume = {69},
  pages = {9--15},
  doi = {10.2307/2312726}
}
"""


@pytest.fixture
def bib(tmp_path: Path) -> Path:
    p = tmp_path / "refs.bib"
    p.write_text(_BIB, encoding="utf-8")
    return p


@pytest.fixture
def never_checks(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("check_references must not run for this output mode")

    monkeypatch.setattr("hallubib.cli.check_references", boom)


@pytest.fixture
def fake_check(monkeypatch):
    def fake(refs, *args, **kwargs):
        return [
            CheckResult(
                reference=r,
                status=Status.AUTO_CORRECTABLE,
                best_match=OnlineRecord(
                    source="openalex",
                    title=r.title,
                    authors=r.authors,
                    year=r.year,
                    volume="70",
                    doi="10.2307/2312726",
                ),
                diffs=[FieldDiff("volume", "69", "70", DiffKind.CORRECTION)],
                suggestions={"volume": "70"},
            )
            for r in refs
        ]

    monkeypatch.setattr("hallubib.cli.check_references", fake)


class TestClearCache:
    def test_removes_cache_and_exits_ok(self, capsys):
        cache.put("ns", "k", {"v": 1})
        assert cache.cache_path().exists()
        assert main(["--clear-cache"]) == 0
        assert not cache.cache_path().exists()
        assert "Cache cleared." in capsys.readouterr().out

    def test_ignores_file_argument(self, bib):
        assert main([str(bib), "--clear-cache"]) == 0


class TestArgumentErrors:
    def test_no_file_and_no_clear_cache(self):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 2

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        assert "hallubib" in capsys.readouterr().out

    def test_missing_file(self, tmp_path, capsys):
        assert main([str(tmp_path / "nope.bib")]) == 1
        assert "not found" in capsys.readouterr().err

    def test_unsupported_suffix(self, tmp_path, capsys):
        p = tmp_path / "notes.txt"
        p.write_text("hello", encoding="utf-8")
        assert main([str(p)]) == 1
        assert "unsupported file type" in capsys.readouterr().err

    def test_bad_output_choice(self, bib):
        with pytest.raises(SystemExit) as exc:
            main([str(bib), "--output", "yaml"])
        assert exc.value.code == 2


class TestEmptyInput:
    def test_no_references_short_circuits(self, tmp_path, capsys, never_checks):
        p = tmp_path / "empty.bib"
        p.write_text("% nothing here\n", encoding="utf-8")
        assert main([str(p)]) == 0
        assert "No references found" in capsys.readouterr().out


class TestCslOutput:
    def test_prints_csl_without_checking(self, bib, capsys, never_checks):
        assert main([str(bib), "--output", "csl"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["id"] == "gs62"
        assert data[0]["DOI"] == "10.2307/2312726"


class TestOutputModes:
    def test_stdout(self, bib, capsys, fake_check):
        assert main([str(bib)]) == 0
        out = capsys.readouterr().out
        assert "Auto-correctable:" in out
        assert "refs.bib" in out

    def test_markdown(self, bib, capsys, fake_check):
        assert main([str(bib), "--output", "md"]) == 0
        out = capsys.readouterr().out
        assert "# hallubib report: refs.bib" in out
        assert "## Auto-correctable" in out

    def test_json(self, bib, capsys, fake_check):
        assert main([str(bib), "--output", "json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["hallubib_version"]
        result = data["results"][0]
        assert result["reference"]["key"] == "gs62"
        assert result["status"] == "Auto-correctable"
        assert result["suggestions"] == {"volume": "70"}

    def test_html_writes_file(self, bib, capsys, fake_check, monkeypatch):
        opened: list[str] = []
        monkeypatch.setattr("hallubib.output.webbrowser.open", opened.append)
        assert main([str(bib), "--output", "html"]) == 0
        err = capsys.readouterr().err
        assert "Report written to" in err
        report = cache.cache_path() / "report.html"
        assert report.exists()
        assert "<!DOCTYPE html>" in report.read_text(encoding="utf-8")
        assert opened == [report.as_uri()]

    def test_progress_goes_to_stderr(self, bib, capsys, fake_check):
        main([str(bib)])
        captured = capsys.readouterr()
        assert "Checking 1 references" in captured.err
        assert "Checking 1 references" not in captured.out


class TestMailto:
    def test_flag_configures_polite_pool(self, bib, capsys, never_checks):
        main([str(bib), "--mailto", "me@example.org", "--output", "csl"])
        assert config.get_config().mailto == "me@example.org"


class TestTexInput:
    def test_tex_accepted(self, tmp_path, capsys, fake_check):
        p = tmp_path / "paper.tex"
        p.write_text(
            r"\bibitem{gs62} Gale, D. and Shapley, L. (1962). "
            r"College Admissions and the Stability of Marriage. "
            r"\emph{The American Mathematical Monthly}, 69, 9--15."
            "\n",
            encoding="utf-8",
        )
        assert main([str(p)]) == 0
        assert "paper.tex" in capsys.readouterr().out


def test_reference_roundtrips_through_parse(bib):
    from hallubib.parser import parse_file

    refs = parse_file(bib)
    assert refs == [
        Reference(
            key="gs62",
            title="College Admissions and the Stability of Marriage",
            authors=[
                Name(family="Gale", given="David"),
                Name(family="Shapley", given="Lloyd S."),
            ],
            type="article-journal",
            year=1962,
            journal="The American Mathematical Monthly",
            volume="69",
            pages="9--15",
            doi="10.2307/2312726",
            raw=refs[0].raw,
        )
    ]
