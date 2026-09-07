"""A format molexp has never heard of, so these tests cannot lean on a real one.

molexp ships no reader: every format arrives from the package that owns it.
Testing with a fake registered reader is therefore not a shortcut — it is the
only honest way to exercise molexp's half of the seam.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from molexp.plugins.metrics_ingest.readers import (
    ReadRequest,
    apply,
    register_reader,
    reset_readers,
    unregister_reader,
)

FAKE_FORMAT = "fake_sim_log"
FAKE_SUFFIX = ".fakelog"


class FakeReader:
    """Reads a trivial ``key value`` table. Cannot push sampling down."""

    format = FAKE_FORMAT
    patterns = (f"**/*{FAKE_SUFFIX}",)
    tailable = False

    def sniff(self, path: Path) -> bool:
        return path.is_file() and path.suffix == FAKE_SUFFIX

    def read(self, path: Path, *, source: str = "", request: ReadRequest | None = None) -> Any:
        def rows():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                key, _, raw = line.partition(" ")
                yield {
                    "t": "scalar",
                    "k": key,
                    "v": float(raw),
                    "tags": {"source": source},
                }

        return apply(request or ReadRequest(), rows())


class StridingReader(FakeReader):
    """Honours ``stride`` inside its own loop, as a real parser would."""

    format = "striding_log"
    patterns = ("**/*.striding",)

    def sniff(self, path: Path) -> bool:
        return path.is_file() and path.suffix == ".striding"

    def read(self, path: Path, *, source: str = "", request: ReadRequest | None = None) -> Any:
        req = request or ReadRequest()
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines[:: max(1, req.stride)]):
            key, _, raw = line.partition(" ")
            yield {
                "t": "scalar",
                "k": key,
                "s": float(index * req.stride),
                "v": float(raw),
                "tags": {"source": source, "strided_by_reader": True},
            }


class BrokenReader:
    """A reader whose dependency is missing — the common real failure."""

    format = "broken_log"
    patterns = ("**/*.broken",)

    def sniff(self, path: Path) -> bool:
        return path.is_file() and path.suffix == ".broken"

    def read(self, path: Path, *, source: str = "", request: Any = None) -> Any:
        raise ImportError("needs a library that is not installed")
        yield  # pragma: no cover


@pytest.fixture(autouse=True)
def registered_readers():
    """Register the fakes for one test, then restore real discovery."""
    for reader in (FakeReader(), StridingReader(), BrokenReader()):
        register_reader(reader)
    yield
    for name in (FAKE_FORMAT, "striding_log", "broken_log"):
        unregister_reader(name)
    reset_readers()


@pytest.fixture
def fake_run(tmp_path: Path) -> Path:
    (tmp_path / f"run{FAKE_SUFFIX}").write_text("energy 1.5\ntemp 300.0\n", encoding="utf-8")
    return tmp_path


def read_wal(run_dir: Path) -> list[dict[str, Any]]:
    from molexp.workspace.execution_dirs import ARTIFACTS

    path = run_dir / ARTIFACTS.name / "metrics.mlp.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
