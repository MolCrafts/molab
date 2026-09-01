"""molrec conformance — test-only extra, never imported from ``src/``.

Install with ``uv sync --extra conformance``. Tests that need the suite
``importorskip``; the src import-guard always runs.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from molexp.plugins.metrics.mlp_names import (
    DEFAULT_MLP_STEM,
    MLP_INDEX_SUFFIX,
    MLP_JSONL_SUFFIX,
    MLP_VL_SUFFIX,
    MLP_ZARR_SUFFIX,
)

_SRC = Path(__file__).resolve().parents[3] / "src" / "molexp"


def _is_molrec_module(name: str | None) -> bool:
    return name == "molrec" or (name is not None and name.startswith("molrec."))


class TestMolrecIsTestOnly:
    def test_src_does_not_import_molrec(self) -> None:
        offenders: list[str] = []
        for path in _SRC.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if _is_molrec_module(alias.name):
                            offenders.append(f"{path.relative_to(_SRC)}:{node.lineno}")
                elif isinstance(node, ast.ImportFrom) and _is_molrec_module(node.module):
                    offenders.append(f"{path.relative_to(_SRC)}:{node.lineno}")
        assert offenders == []

    def test_conformance_suite_skips_unclaimed_modules(self) -> None:
        pytest.importorskip("molrec")
        from molrec import ConformanceSuite, Implementation

        class MolexpHost(Implementation):
            name = "molexp"
            version = "0"

        report = ConformanceSuite(MolexpHost()).run()
        assert not any(row.status in {"pass", "fail", "error"} for row in report.results)


class TestHostLayoutMatchesProtocol:
    def test_filename_constants(self) -> None:
        host = pytest.importorskip("molrec.host")
        assert DEFAULT_MLP_STEM == host.DEFAULT_MLP_STEM
        assert MLP_JSONL_SUFFIX == host.MLP_JSONL_SUFFIX
        assert MLP_ZARR_SUFFIX == host.MLP_ZARR_SUFFIX
        assert MLP_INDEX_SUFFIX == host.MLP_INDEX_SUFFIX
        assert MLP_VL_SUFFIX == host.MLP_VL_SUFFIX

    def test_writer_persists_jsonl_not_zarr(self, run) -> None:
        with run.start() as ctx:
            ctx.metrics.scalar("train/loss", 0.25, step=1)

        eid = run.current_execution_id
        assert eid is not None
        exec_dir = Path(run.run_dir) / "executions" / eid
        wal = exec_dir / "artifacts" / "metrics.mlp.jsonl"
        record = json.loads(wal.read_text().strip())
        assert record["k"] == "train/loss"
        assert record["v"] == 0.25
        assert not (exec_dir / "metrics.mlp.zarr").exists()
        assert not (exec_dir / "metrics.mlp.index.json").exists()
