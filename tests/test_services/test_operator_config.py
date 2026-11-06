"""Operator-config file API — ``load`` / ``save_operator_config`` / ``set_operator_values``.

Spec ``vision-loop-03-settings-operator-config``: the services layer owns the
one write path for ``~/.molab/config.json`` (atomic tmp+rename). The loader is
shared by CLI, server and auth; the writer is CLI-only (the server only reads). drop-harness-01-src (D86) removed the agent
model/key bridge into ``molab.config``; ``TestOperatorConfigSurface`` pins that
only the file API is left.

Every test points the writer at a tmp path — the operator's real
``~/.molab/config.json`` is never read or written.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import molcfg
import pytest

import molab
from molab.services import operator_config
from molab.services.operator_config import (
    load_operator_config,
    save_operator_config,
    set_operator_values,
)

_MODEL = "deepseek:deepseek-v4-flash"
_RAW_KEY = "sk-operator-secret-key-9876"


def _boom(*args: object, **kwargs: object) -> None:
    raise OSError("injected rename failure")


class TestSaveOperatorConfig:
    """``save_operator_config(config, path=None)`` — the atomic file writer."""

    def test_save_round_trips_through_loader(self, tmp_path: Path) -> None:
        path = tmp_path / "config.json"
        config = {"agent": {"model": _MODEL, "deepseek_api_key": _RAW_KEY}}

        save_operator_config(config, path=path)

        assert load_operator_config(path) == config

    def test_save_sets_owner_only_permissions(self, tmp_path: Path) -> None:
        """The file stores API keys — 0600, same as the CLI idiom it replaces."""
        path = tmp_path / "config.json"

        save_operator_config({"agent": {"deepseek_api_key": _RAW_KEY}}, path=path)

        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_save_failure_leaves_original_intact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Atomicity: a failed rename never corrupts / truncates the target."""
        path = tmp_path / "config.json"
        save_operator_config({"agent": {"model": _MODEL}}, path=path)
        before = path.read_bytes()

        monkeypatch.setattr(os, "replace", _boom)
        monkeypatch.setattr(os, "rename", _boom)
        with pytest.raises(OSError):
            save_operator_config({"agent": {"model": "other:model"}}, path=path)

        assert path.read_bytes() == before
        assert load_operator_config(path) == {"agent": {"model": _MODEL}}


class TestSetOperatorValues:
    """``set_operator_values(updates, *, unset=None, path=None)`` on dotted keys."""

    def test_set_creates_nested_agent_section(self, tmp_path: Path) -> None:
        path = tmp_path / "config.json"

        set_operator_values({"agent.model": _MODEL}, path=path)

        assert load_operator_config(path) == {"agent": {"model": _MODEL}}

    def test_set_preserves_unrelated_sections(self, tmp_path: Path) -> None:
        path = tmp_path / "config.json"
        save_operator_config(
            {"defaults": {"shell": "bash"}, "agent": {"instructions": "be brief"}},
            path=path,
        )

        set_operator_values({"agent.model": _MODEL}, path=path)

        loaded = load_operator_config(path)
        assert loaded["defaults"] == {"shell": "bash"}
        assert loaded["agent"] == {"instructions": "be brief", "model": _MODEL}

    def test_unset_removes_only_the_named_key(self, tmp_path: Path) -> None:
        path = tmp_path / "config.json"
        set_operator_values(
            {"agent.model": _MODEL, "agent.deepseek_api_key": _RAW_KEY},
            path=path,
        )

        set_operator_values({}, unset=["agent.deepseek_api_key"], path=path)

        loaded = load_operator_config(path)
        agent = loaded["agent"]
        assert isinstance(agent, dict)
        assert agent.get("model") == _MODEL
        assert "deepseek_api_key" not in agent
        assert _RAW_KEY not in path.read_text()


class TestOperatorConfigSurface:
    """Only the file API is left; the agent bridge went with the harness (D86)."""

    @pytest.mark.parametrize(
        "name",
        [
            "load_operator_config",
            "save_operator_config",
            "set_operator_values",
            "OPERATOR_CONFIG_PATH",
        ],
    )
    def test_the_file_api_is_kept(self, name: str) -> None:
        assert hasattr(operator_config, name)

    @pytest.mark.parametrize(
        "name",
        [
            "bridge_operator_config",
            "configured_agent_model",
            "configured_agent_models",
            "configured_api_keys",
            "resolve_configured_model",
            "resolve_configured_models",
            "AGENT_MODEL_KEY",
            "AGENT_MODELS_KEY",
        ],
    )
    def test_the_agent_bridge_is_gone(self, name: str) -> None:
        assert not hasattr(operator_config, name)
        assert name not in operator_config.__all__

    def test_molab_config_is_kept(self) -> None:
        assert isinstance(molab.config, molcfg.Config)
