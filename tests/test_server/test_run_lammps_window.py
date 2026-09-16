"""``/runs/{id}/lammps-log`` parses the tail of an oversized log, not the whole file."""

from __future__ import annotations

from pathlib import Path

import pytest

_STAGE = (
    "Per MPI rank memory allocation (min/avg/max) = 1 | 1 | 1 Mbytes\n"
    "Step Temp E_pair TotEng Press\n"
    "{step} 300.0 -1.5 -1.0 0.5\n"
    "Loop time of 1.0 on 1 procs\n"
)


def _write_log(run, rel: str, text: str) -> Path:
    target = Path(str(run.run_dir)) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


@pytest.fixture
def url(project, experiment, run):
    return f"/api/projects/{project.id}/experiments/{experiment.id}/runs/{run.id}/lammps-log"


class TestSmallLog:
    def test_parses_stages_and_version(self, client, run, url):
        _write_log(run, "log.lammps", "LAMMPS (2 Aug 2023)\n" + _STAGE.format(step=0))
        body = client.get(url, params={"path": "log.lammps"}).json()
        assert body["version"] == "LAMMPS (2 Aug 2023)"
        assert body["nStages"] == 1
        assert body["stages"][0]["columns"] == ["Step", "Temp", "E_pair", "TotEng", "Press"]
        assert body["truncated"] is False
        assert body["bytesParsed"] > 0

    def test_missing_log_is_404(self, client, url):
        assert client.get(url, params={"path": "nope.log"}).status_code == 404

    def test_path_escape_is_refused(self, client, url):
        assert client.get(url, params={"path": "../../etc/passwd"}).status_code == 400


class TestOversizedLog:
    def test_tail_is_parsed_and_marked_truncated(self, client, run, url, monkeypatch):
        # Patch the ceiling rather than writing 32 MB.
        monkeypatch.setattr("molexp.server.routes.run.LAMMPS_LOG_MAX_BYTES", 4096)
        text = "LAMMPS (2 Aug 2023)\n" + "".join(_STAGE.format(step=i) for i in range(200))
        _write_log(run, "log.lammps", text)

        body = client.get(url, params={"path": "log.lammps"}).json()
        assert body["truncated"] is True
        assert body["bytesParsed"] <= 4096
        # The banner lives on line 1, which a tail window never contains — so
        # the route reports no version rather than inventing one from a
        # mid-file line.
        assert body["version"] is None
        # Still useful: the latest stages parsed out of the tail.
        assert body["nStages"] > 0
