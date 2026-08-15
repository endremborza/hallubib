from pathlib import Path

import pytest

from hallubib import cache, config
from hallubib.sources import _http


class TestConfigure:
    def test_returns_updated_config(self):
        cfg = config.configure(mailto="a@b.c")
        assert cfg.mailto == "a@b.c"
        assert config.get_config().mailto == "a@b.c"

    def test_bumps_generation(self):
        before = config.generation()
        config.configure(timeout=1.0)
        assert config.generation() > before

    def test_cache_dir_coerced_to_path(self, tmp_path: Path):
        config.configure(cache_dir=str(tmp_path / "c"))
        assert config.get_config().cache_dir == tmp_path / "c"

    def test_cache_dir_none_left_alone(self):
        config.configure(cache_dir=None)
        assert config.get_config().cache_dir is None

    def test_cache_dir_overrides_xdg(self, tmp_path: Path):
        config.configure(cache_dir=tmp_path / "explicit")
        cache.put("ns", "k", {"v": 1})
        assert (tmp_path / "explicit" / "ns" / "k.json").exists()

    def test_partial_override_keeps_other_fields(self):
        config.configure(mailto="a@b.c", timeout=3.0)
        config.configure(timeout=9.0)
        cfg = config.get_config()
        assert cfg.mailto == "a@b.c"
        assert cfg.timeout == 9.0

    def test_unknown_field_rejected(self):
        with pytest.raises(TypeError):
            config.configure(nonsense=1)


class TestEnvDefaults:
    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv("HALLUBIB_MAILTO", "env@example.org")
        monkeypatch.setenv("S2_API_KEY", "secret")
        monkeypatch.setenv("OPENALEX_API_KEY", "oa-secret")
        cfg = config._from_env()
        assert cfg.mailto == "env@example.org"
        assert cfg.s2_api_key == "secret"
        assert cfg.openalex_api_key == "oa-secret"

    def test_absent_env_is_none(self, monkeypatch):
        monkeypatch.delenv("HALLUBIB_MAILTO", raising=False)
        monkeypatch.delenv("S2_API_KEY", raising=False)
        cfg = config._from_env()
        assert cfg.mailto is None
        assert cfg.s2_api_key is None


class TestSessionFollowsConfig:
    def test_user_agent_has_version(self):
        config.configure(mailto=None)
        ua = _http.session().headers["User-Agent"]
        assert ua.startswith("hallubib/")
        assert "mailto" not in ua

    def test_mailto_enters_user_agent(self):
        config.configure(mailto="polite@example.org")
        assert "mailto:polite@example.org" in _http.session().headers["User-Agent"]

    def test_session_rebuilt_on_reconfigure(self):
        config.configure(mailto="first@example.org")
        first = _http.session()
        config.configure(mailto="second@example.org")
        second = _http.session()
        assert first is not second
        assert "second@example.org" in second.headers["User-Agent"]

    def test_session_reused_without_reconfigure(self):
        assert _http.session() is _http.session()
