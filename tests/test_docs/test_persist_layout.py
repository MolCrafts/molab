"""Docs and constitution no longer name deleted persist surfaces."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN = (
    "harness.sqlite",
    "ops/run.json",
    "metrics.mlp.zarr",
    "metrics.mlp.index.json",
)
_SCAN = (
    _ROOT / "CLAUDE.md",
    _ROOT / "docs/en/concept/workspace.md",
    _ROOT / "docs/en/concept/assets-and-reproducibility.md",
    _ROOT / "docs/en/getting-started/tracked-runs.md",
    _ROOT / "docs/en/guide/workspace-architecture.md",
    _ROOT / "docs/en/guide/workspace-api.md",
    _ROOT / "docs/en/guide/workflow-persistence.md",
    _ROOT / "docs/en/architecture/harness.md",
    _ROOT / "docs/en/architecture/plan-mode.md",
    _ROOT / "docs/en/guide/plan-mode.md",
    _ROOT / "docs/en/plugins.md",
)


class TestPersistLayoutDocs:
    def test_listed_docs_do_not_name_deleted_surfaces(self) -> None:
        missing = [str(path) for path in _SCAN if not path.is_file()]
        assert not missing, missing
        hits: list[str] = []
        for path in _SCAN:
            text = path.read_text(encoding="utf-8")
            for token in _FORBIDDEN:
                if token in text:
                    hits.append(f"{path.relative_to(_ROOT)}: {token}")
        assert hits == []
