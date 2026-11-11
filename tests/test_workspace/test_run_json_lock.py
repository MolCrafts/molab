"""Lost-update protection for the run record read-modify-write cycle.

The run record (``index.md``) is written by several uncoordinated writers (server process,
foreground CLI, detached workers). ``Run._update_metadata`` must reload the
on-disk state and apply the partial update under an advisory file lock, so two
writers touching *distinct* fields never drop each other's updates. (The
``file_lock`` primitive itself — timeout / no-fcntl degradation — is owned by
``tests/test_atomicio.py``.)
"""

from __future__ import annotations

from molab.workspace import Workspace
from tests.support.records import read_record


def _read_run_json(run) -> dict:
    return read_record(run.run_dir)


def _second_handle(tmp_path, run):
    """Load an independent Run handle for the same on-disk run."""
    ws = Workspace(root=tmp_path, name="Test Lab")
    project = ws.list_projects()[0]
    experiment = project.list_experiments()[0]
    other = next(r for r in experiment.list_runs() if r.id == run.id)
    assert other is not run
    return other


class TestRunMetadataRmw:
    def test_concurrent_updates_to_distinct_fields_do_not_clobber(self, tmp_path, run) -> None:
        run.materialize()
        other = _second_handle(tmp_path, run)

        run._update_metadata(target="cluster-a")
        other._update_metadata(inputs=("asset-1",))

        data = _read_run_json(run)
        assert data["target"] == "cluster-a"
        assert data["inputs"] == ["asset-1"]
