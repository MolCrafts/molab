"""Unit tests for :mod:`molexp.plugins.metrics_ingest.ingest`.

LAMMPS logs are read by molpy's metric reader, a direct dependency; what is
under test here is the ingest around it — selection, skips, the buffer it
writes and what it leaves alone.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from molexp.plugins.metrics_ingest import ingest as ingest_mod
from molexp.plugins.metrics_ingest import lammps as lammps_mod
from molexp.plugins.metrics_ingest.detect import LogFormat
from molexp.plugins.metrics_ingest.ingest import ingest_run
from molexp.plugins.metrics_ingest.tabular import ColumnMapping

LAMMPS_LOG = """LAMMPS (2 Aug 2023)
Per MPI rank memory allocation (min/avg/max) = 3.5 | 3.5 | 3.5 Mbytes
   Step          Temp
         0   300.00
       100   298.00
Loop time of 4.21 on 4 procs for 200 steps with 1000 atoms
Total wall time: 0:00:04
"""


@pytest.fixture
def lammps_run(tmp_path: Path) -> Path:
    (tmp_path / "log.lammps").write_text(LAMMPS_LOG, encoding="utf-8")
    return tmp_path


def _read_lines(run_dir: Path) -> list[dict[str, Any]]:
    stream = run_dir / "metrics.mlp.jsonl"
    return [
        json.loads(line) for line in stream.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


class TestIngestRunWritesOnlyTheBuffer:
    def test_writes_metrics_and_the_host_series_cache(self, lammps_run: Path) -> None:
        result = ingest_run(lammps_run)

        assert result.ingested == {LogFormat.LAMMPS_LOG: 2}
        assert (lammps_run / "metrics.mlp.jsonl").is_file()
        assert (lammps_run / "metrics.mlp.index.json").is_file()
        assert (lammps_run / "metrics.mlp.zarr" / "zarr.json").is_file()

    def test_never_writes_molrec_sections(self, lammps_run: Path) -> None:
        """A Run is a host, not a MolRec record.

        Writing ``meta/`` or ``status/`` here would make every ingested run
        claim to be a record. This test is the gate on that invariant.
        """
        ingest_run(lammps_run)

        assert not (lammps_run / "meta").exists()
        assert not (lammps_run / "status").exists()
        assert not (lammps_run / "method").exists()

    def test_leaves_the_source_log_untouched(self, lammps_run: Path) -> None:
        before = (lammps_run / "log.lammps").read_bytes()
        ingest_run(lammps_run)

        assert (lammps_run / "log.lammps").read_bytes() == before


class TestIngestRunSkips:
    def test_records_a_missing_dependency_without_raising(
        self, lammps_run: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def unavailable(path: Path, *, source: str) -> Any:
            raise ImportError("no molpy here")

        monkeypatch.setattr(ingest_mod, "thermo_records", unavailable)
        result = ingest_run(lammps_run)

        assert result.did_ingest is False
        assert len(result.skipped) == 1
        assert "no molpy here" in result.skipped[0].reason
        assert not (lammps_run / "metrics.mlp.jsonl").exists()

    def test_skips_csv_without_a_mapping(self, tmp_path: Path) -> None:
        (tmp_path / "curve.csv").write_text("step,loss\n1,0.5\n", encoding="utf-8")
        result = ingest_run(tmp_path)

        assert result.did_ingest is False
        assert result.skipped[0].format is LogFormat.CSV
        assert "ColumnMapping" in result.skipped[0].reason

    def test_ingests_csv_with_a_mapping(self, tmp_path: Path) -> None:
        (tmp_path / "curve.csv").write_text("step,loss,note\n1,0.5,a\n2,0.25,b\n", encoding="utf-8")
        result = ingest_run(
            tmp_path, csv_mapping=ColumnMapping(step_column="step", series_columns=("loss",))
        )

        assert result.ingested == {LogFormat.CSV: 2}
        records = _read_lines(tmp_path)
        assert [record["k"] for record in records] == ["csv/loss", "csv/loss"]
        assert [record["s"] for record in records] == [1.0, 2.0]

    def test_honours_an_explicit_format_selection(self, tmp_path: Path) -> None:
        (tmp_path / "curve.csv").write_text("step,loss\n1,0.5\n", encoding="utf-8")
        result = ingest_run(tmp_path, formats=set())

        assert result.did_ingest is False
        assert result.skipped[0].reason == "not selected by the operator"

    def test_empty_directory_is_a_clean_no_op(self, tmp_path: Path) -> None:
        result = ingest_run(tmp_path)

        assert result.did_ingest is False
        assert result.skipped == []
        assert not (tmp_path / "metrics.mlp.jsonl").exists()


class TestLammpsSource:
    def test_tags_every_record_with_the_log_path_under_the_run(self, tmp_path: Path) -> None:
        (tmp_path / "md").mkdir()
        (tmp_path / "md" / "log.lammps").write_text(LAMMPS_LOG, encoding="utf-8")
        ingest_run(tmp_path)

        assert {record["tags"]["source"] for record in _read_lines(tmp_path)} == {"md/log.lammps"}


class TestIngestIsAdditive:
    def test_a_second_ingest_appends_rather_than_truncating(self, lammps_run: Path) -> None:
        ingest_run(lammps_run)
        ingest_run(lammps_run)

        assert len(_read_lines(lammps_run)) == 4


@pytest.mark.parametrize("module", [ingest_mod, lammps_mod])
def test_module_never_imports_molpy_at_module_scope(module: Any) -> None:
    """molpy is heavy at import time — the import stays inside the functions."""
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "\nimport molpy" not in source
    assert "\nfrom molpy" not in source
