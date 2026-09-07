"""Discovery and persistence, with no format knowledge in molexp.

These exercise molexp's half of the seam — walking a run, dispatching to
whatever reader claimed a file, and writing the WAL. What a LAMMPS thermo
table maps to is molpy's business and is tested there.
"""

from __future__ import annotations

from pathlib import Path

from molexp.plugins.metrics_ingest import detect_log_formats, ingest_run
from molexp.workspace.execution_dirs import ARTIFACTS

FAKE_SUFFIX = ".fakelog"


def _wal(run_dir: Path) -> Path:
    return run_dir / ARTIFACTS.name / "metrics.mlp.jsonl"


def _read_wal(run_dir: Path) -> list[dict]:
    import json

    return [json.loads(x) for x in _wal(run_dir).read_text().splitlines() if x.strip()]


class TestDiscovery:
    def test_reports_a_claimed_file(self, fake_run: Path) -> None:
        assert [hit.format for hit in detect_log_formats(fake_run)] == ["fake_sim_log"]

    def test_skips_hidden_directories(self, tmp_path: Path) -> None:
        hidden = tmp_path / ".cache"
        hidden.mkdir()
        (hidden / f"x{FAKE_SUFFIX}").write_text("a 1\n", encoding="utf-8")
        assert detect_log_formats(tmp_path) == []

    def test_respects_max_depth(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / f"x{FAKE_SUFFIX}").write_text("a 1\n", encoding="utf-8")
        assert detect_log_formats(tmp_path, max_depth=2) == []
        assert len(detect_log_formats(tmp_path, max_depth=5)) == 1

    def test_an_unreadable_format_is_simply_not_reported(self, tmp_path: Path) -> None:
        (tmp_path / "notes.md").write_text("# notes", encoding="utf-8")
        assert detect_log_formats(tmp_path) == []


class TestIngestWritesOnlyTheBuffer:
    def test_writes_jsonl_in_the_products_dir(self, fake_run: Path) -> None:
        result = ingest_run(fake_run)
        assert result.records == 2
        assert _wal(fake_run).is_file()
        assert {row["k"] for row in _read_wal(fake_run)} == {"energy", "temp"}

    def test_never_writes_molrec_sections(self, fake_run: Path) -> None:
        """A Run is a host, not a MolRec record."""
        ingest_run(fake_run)
        assert not (fake_run / "meta").exists()
        assert not (fake_run / "status").exists()
        assert not list(fake_run.rglob("*.mlp.zarr"))
        assert not list(fake_run.rglob("metrics.mlp.index.json"))

    def test_a_second_ingest_appends_rather_than_truncating(self, fake_run: Path) -> None:
        ingest_run(fake_run)
        ingest_run(fake_run)
        assert len(_read_wal(fake_run)) == 4

    def test_tags_carry_the_source_path(self, fake_run: Path) -> None:
        ingest_run(fake_run)
        assert {row["tags"]["source"] for row in _read_wal(fake_run)} == {"run.fakelog"}


class TestIngestNeverFailsTheCaller:
    def test_a_missing_dependency_is_a_skip_not_an_exception(self, tmp_path: Path) -> None:
        (tmp_path / "sim.broken").write_text("x", encoding="utf-8")
        result = ingest_run(tmp_path)
        assert result.records == 0
        assert len(result.skipped) == 1
        assert "not installed" in result.skipped[0].reason

    def test_one_broken_source_does_not_stop_the_others(self, fake_run: Path) -> None:
        (fake_run / "sim.broken").write_text("x", encoding="utf-8")
        result = ingest_run(fake_run)
        assert result.records == 2
        assert [skip.format for skip in result.skipped] == ["broken_log"]

    def test_a_run_with_nothing_to_read_is_not_an_error(self, tmp_path: Path) -> None:
        result = ingest_run(tmp_path)
        assert result.records == 0
        assert not result.did_ingest
