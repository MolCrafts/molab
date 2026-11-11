"""Node records: every task's inputs and outputs, deduplicated, and rerun of one node.

A run keeps one content-addressed value store, ``<run_dir>/values/``. Each
journal record names its output and every runtime input by ref
(``sha256:<hex>``); an upstream output and the downstream input it feeds are
the same bytes, so they are the same file. Resume and ``rerun(only=...)``
seed from those refs (pickled values included), and a rerun of one task runs
exactly that task with the inputs its predecessor recorded, leaving its
downstream tasks ``skipped``.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

import molab as me
from molab.workflow import (
    Next,
    RunFailedError,
    RunNotExecutableError,
    Workflow,
    read_journal,
    read_outputs,
)
from molab.workflow._engine.values import UnrecordableValueError, ValueStore
from molab.workflow.execute import execute_run
from molab.workspace.validate import validate_workspace

_CALLS: dict[str, int] = {}
_SWITCH = {"fail_b": False}


def _bump(name: str) -> None:
    _CALLS[name] = _CALLS.get(name, 0) + 1


@pytest.fixture(autouse=True)
def _reset() -> None:
    _CALLS.clear()
    _SWITCH["fail_b"] = False


class Molecule:
    """A picklable, non-JSON task output (stands in for ``molpy.Atomistic``)."""

    def __init__(self, atoms: list[str]) -> None:
        self.atoms = atoms

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Molecule) and other.atoms == self.atoms

    def __hash__(self) -> int:
        return hash(tuple(self.atoms))

    def __repr__(self) -> str:
        return f"Molecule({len(self.atoms)} atoms)"


def _chain() -> Workflow:
    """``a -> b -> c``; ``b`` fails while the switch is on."""
    wf = Workflow(name="chain")

    @wf.task
    def a(x: int) -> int:
        _bump("a")
        return x + 1

    @wf.task(depends_on=["a"])
    def b(a: int) -> int:
        _bump("b")
        if _SWITCH["fail_b"]:
            raise RuntimeError("AM1 charges did not converge")
        return a * 10

    @wf.task(depends_on=["b"])
    def c(b: int) -> int:
        _bump("c")
        return b + 5

    return wf


def _molecule_chain() -> Workflow:
    """``build`` returns a pickled object; ``charge`` fails while the switch is on."""
    wf = Workflow(name="molecules")

    @wf.task
    def build(x: int) -> Molecule:
        _bump("build")
        return Molecule(["C"] * x)

    @wf.task(depends_on=["build"])
    def charge(build: Molecule) -> int:
        _bump("charge")
        if _SWITCH["fail_b"]:
            raise RuntimeError("AM1 charges did not converge")
        return len(build.atoms)

    return wf


def _chain_with_picture() -> Workflow:
    """:func:`_chain` plus ``picture``, which needs only the run's parameter."""
    wf = _chain()

    @wf.task
    def picture(x: int) -> str:
        _bump("picture")
        return f"x={x}"

    return wf


def _drop_config(run, execution_id: str) -> None:
    path = run.execution_dir(execution_id) / "execution.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    loaded["environment"].pop("config_hash", None)
    path.write_text(json.dumps(loaded), encoding="utf-8")


def _strip_to_adopted(run, execution_id: str) -> None:
    """Make *execution_id* look adopted: no journal, no config_hash."""
    (run.execution_dir(execution_id) / "workflow.json").unlink()
    _drop_config(run, execution_id)


def _run(tmp_path: Path, params: dict | None = None):
    ws = me.Workspace(tmp_path / "ws", name="lab")
    return ws.add_project("p").add_experiment("e").add_run(params=params or {"x": 2})


def _raw_journal(run, execution_id: str) -> dict:
    return json.loads((run.execution_dir(execution_id) / "workflow.json").read_text())


def _records(doc: dict) -> dict[str, dict]:
    return {task["task_id"]: task for task in doc["task_configs"]}


def _value_files(run) -> list[Path]:
    root = run.values_dir()
    return sorted(root.iterdir()) if root.exists() else []


def _file_of(run, ref: str) -> list[Path]:
    digest = ref.removeprefix("sha256:")
    return [path for path in _value_files(run) if path.stem == digest]


def _fail_once(workflow: Workflow, run) -> None:
    _SWITCH["fail_b"] = True
    with pytest.raises(RunFailedError):
        execute_run(workflow, run)
    _SWITCH["fail_b"] = False


# ── The value store ──────────────────────────────────────────────────────────


class TestValueStore:
    def test_json_value_is_stored_once_under_its_digest(self, tmp_path: Path) -> None:
        store = ValueStore(tmp_path / "values")
        ref = store.put({"b": 1, "a": [1, 2]})
        again = store.put({"a": [1, 2], "b": 1})
        assert ref == again
        files = list((tmp_path / "values").iterdir())
        assert [path.name for path in files] == [f"{ref.removeprefix('sha256:')}.json"]
        assert hashlib.sha256(files[0].read_bytes()).hexdigest() == ref.removeprefix("sha256:")
        assert store.get(ref) == {"a": [1, 2], "b": 1}

    def test_non_json_value_is_pickled_and_round_trips(self, tmp_path: Path) -> None:
        store = ValueStore(tmp_path / "values")
        ref = store.put(Molecule(["C", "H"]))
        [path] = (tmp_path / "values").iterdir()
        assert path.suffix == ".pkl"
        assert store.get(ref) == Molecule(["C", "H"])

    def test_a_tuple_is_not_coerced_to_a_list(self, tmp_path: Path) -> None:
        store = ValueStore(tmp_path / "values")
        assert store.get(store.put((1, 2))) == (1, 2)

    def test_an_unpicklable_value_is_unrecordable(self, tmp_path: Path) -> None:
        store = ValueStore(tmp_path / "values")
        with pytest.raises(UnrecordableValueError):
            store.put(threading.Lock())

    def test_a_missing_ref_fails_loudly(self, tmp_path: Path) -> None:
        store = ValueStore(tmp_path / "values")
        with pytest.raises(FileNotFoundError):
            store.get("sha256:" + "0" * 64)


# ── The journal records refs, deduplicated ───────────────────────────────────


class TestJournalRecordsRefs:
    def test_upstream_output_and_downstream_input_share_one_file(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        execute_run(_chain(), run)
        records = _records(_raw_journal(run, "e01"))

        a_out = records["a"]["output_ref"]
        assert records["b"]["input_refs"]["upstream"] == {"a": a_out}
        assert records["c"]["input_refs"]["upstream"] == {"b": records["b"]["output_ref"]}
        assert len(_file_of(run, a_out)) == 1
        assert "root" in records["a"]["input_refs"]
        assert "config" in records["a"]["input_refs"]

    def test_journal_holds_refs_not_values(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        execute_run(_chain(), run)
        for record in _raw_journal(run, "e01")["task_configs"]:
            assert "outputs" not in record
            assert "outputs_lossy" not in record
            assert record["output_ref"].startswith("sha256:")

    def test_read_journal_still_presents_json_outputs(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        execute_run(_chain(), run)
        presented = _records(read_journal(run, "e01"))
        assert {name: record["outputs"] for name, record in presented.items()} == {
            "a": 3,
            "b": 30,
            "c": 35,
        }
        assert read_outputs(run, "e01") == {"a": 3, "b": 30, "c": 35}

    def test_two_attempts_with_the_same_values_add_no_files(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        execute_run(_chain(), run)
        before = _value_files(run)
        execute_run(_chain(), run, rerun=True, fresh=True)
        assert _value_files(run) == before
        assert _CALLS["a"] == 2

    def test_a_failed_task_records_its_inputs(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        _fail_once(_chain(), run)
        records = _records(_raw_journal(run, "e01"))
        assert records["b"]["status"] == "failed"
        assert records["b"]["input_refs"]["upstream"] == {"a": records["a"]["output_ref"]}
        assert "output_ref" not in records["b"]


class TestPickledOutputs:
    def test_pickled_output_is_recorded_with_a_preview(self, tmp_path: Path) -> None:
        run = _run(tmp_path, {"x": 3})
        execute_run(_molecule_chain(), run)
        raw = _records(_raw_journal(run, "e01"))["build"]
        assert raw["output_encoding"] == "pickle"
        assert _file_of(run, raw["output_ref"])[0].suffix == ".pkl"

        presented = _records(read_journal(run, "e01"))["build"]
        assert "outputs" not in presented
        assert presented["outputs_pickled"] is True
        assert presented["output_preview"] == "Molecule(3 atoms)"
        assert read_outputs(run, "e01")["build"] == Molecule(["C"] * 3)

    def test_resume_seeds_a_pickled_output(self, tmp_path: Path) -> None:
        run = _run(tmp_path, {"x": 3})
        _fail_once(_molecule_chain(), run)

        result = execute_run(_molecule_chain(), run, resume=True)

        assert result.outputs["charge"] == 3
        assert _CALLS == {"build": 1, "charge": 2}
        doc = _raw_journal(run, "e02")
        seeded = doc["seeded_from"]["build"]
        assert seeded["execution_id"] == "e01"
        assert seeded["ref"] == _records(_raw_journal(run, "e01"))["build"]["output_ref"]
        assert doc["selected_tasks"] is None


# ── Rerun one node ───────────────────────────────────────────────────────────


class TestRerunOneTask:
    def test_rerun_runs_only_the_selected_failed_task(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        _fail_once(_chain(), run)
        assert _CALLS == {"a": 1, "b": 1}

        result = execute_run(_chain(), run, rerun=True, only=("b",))

        assert _CALLS == {"a": 1, "b": 2}
        assert result.outputs["b"] == 30
        record = run.execution("e02")
        assert record.selected_tasks == ("b",)
        doc = _raw_journal(run, "e02")
        assert doc["selected_tasks"] == ["b"]
        records = _records(doc)
        assert records["a"]["status"] == "completed"
        assert records["a"]["seeded_from"] == "e01"
        assert records["b"]["status"] == "completed"
        assert records["c"]["status"] == "skipped"
        assert "not selected" in records["c"]["reason"]

    def test_downstream_of_the_selected_task_is_never_called(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        execute_run(_chain(), run)
        assert _CALLS == {"a": 1, "b": 1, "c": 1}

        execute_run(_chain(), run, rerun=True, fresh=True, only=("b",))

        assert _CALLS == {"a": 1, "b": 2, "c": 1}
        assert _records(_raw_journal(run, "e02"))["c"]["status"] == "skipped"

    def test_selected_task_reads_its_upstream_from_the_predecessor_record(
        self, tmp_path: Path
    ) -> None:
        run = _run(tmp_path)
        _fail_once(_chain(), run)
        # Point a's record at another value: the rerun must consume the record.
        store = ValueStore(run.values_dir())
        doc = _raw_journal(run, "e01")
        _records(doc)["a"]["output_ref"] = store.put(7)
        (run.execution_dir("e01") / "workflow.json").write_text(json.dumps(doc))

        result = execute_run(_chain(), run, rerun=True, only=("b",))

        assert result.outputs["b"] == 70
        assert _CALLS["a"] == 1

    def test_refuses_when_an_upstream_value_is_missing(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        _fail_once(_chain(), run)
        a_ref = _records(_raw_journal(run, "e01"))["a"]["output_ref"]
        for path in _file_of(run, a_ref):
            path.unlink()

        with pytest.raises(RunNotExecutableError, match="'a'"):
            execute_run(_chain(), run, rerun=True, only=("b",))
        assert [item.id for item in run.executions if item.status.value == "queued"] == []
        assert _CALLS == {"a": 1, "b": 1}

    def test_new_task_runs_alone_on_an_unjournalled_predecessor(self, tmp_path: Path) -> None:
        # An adopted attempt: no journal and no config_hash. A task added to the
        # workflow since then needs nothing from it, so a partial rerun of that
        # task alone has nothing to mix and runs; the rest is not re-executed.
        run = _run(tmp_path)
        execute_run(_chain(), run)
        _strip_to_adopted(run, "e01")
        _CALLS.clear()

        result = execute_run(_chain_with_picture(), run, rerun=True, only=("picture",))

        assert _CALLS == {"picture": 1}
        assert result.outputs["picture"] == "x=2"
        records = _records(_raw_journal(run, "e02"))
        assert records["picture"]["status"] == "completed"
        assert {records[name]["status"] for name in ("a", "b", "c")} == {"skipped"}

    def test_unjournalled_predecessor_still_refuses_a_task_needing_upstream(
        self, tmp_path: Path
    ) -> None:
        run = _run(tmp_path)
        execute_run(_chain(), run)
        _strip_to_adopted(run, "e01")

        with pytest.raises(RunNotExecutableError, match="'a'"):
            execute_run(_chain(), run, rerun=True, only=("b",))

    def test_journalled_predecessor_without_config_hash_is_still_refused(
        self, tmp_path: Path
    ) -> None:
        run = _run(tmp_path)
        execute_run(_chain(), run)
        _drop_config(run, "e01")

        with pytest.raises(RunNotExecutableError, match="config_hash"):
            execute_run(_chain_with_picture(), run, rerun=True, only=("picture",))

    def test_unknown_task_is_refused(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        execute_run(_chain(), run)
        with pytest.raises(ValueError, match="nope"):
            execute_run(_chain(), run, rerun=True, only=("nope",))

    def test_only_requires_rerun(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        execute_run(_chain(), run)
        with pytest.raises(ValueError, match="rerun"):
            execute_run(_chain(), run, resume=True, only=("b",))

    def test_rerun_of_a_task_with_a_pickled_input(self, tmp_path: Path) -> None:
        run = _run(tmp_path, {"x": 4})
        _fail_once(_molecule_chain(), run)

        result = execute_run(_molecule_chain(), run, rerun=True, only=("charge",))

        assert result.outputs["charge"] == 4
        assert _CALLS == {"build": 1, "charge": 2}


def _routed() -> Workflow:
    """``route`` sends ``{"payload": x}`` to the dep-less ``dst`` along a branch."""
    wf = Workflow(name="routed", entry="route")

    @wf.task(routes={"go": "dst", "stop": "_end"})
    def route(x: int) -> tuple[dict, Next]:
        _bump("route")
        return {"payload": x}, Next("go")

    @wf.task
    def dst(payload: int) -> int:
        _bump("dst")
        if _SWITCH["fail_b"]:
            raise RuntimeError("not yet")
        return payload * 2

    return wf


class TestDeliveredInputs:
    def test_rerun_hands_the_selected_task_its_recorded_delivered_value(
        self, tmp_path: Path
    ) -> None:
        run = _run(tmp_path, {"x": 21})
        _fail_once(_routed(), run)
        assert "delivered" in _records(_raw_journal(run, "e01"))["dst"]["input_refs"]

        result = execute_run(_routed(), run, rerun=True, only=("dst",))

        assert result.outputs["dst"] == 42
        assert _CALLS == {"route": 1, "dst": 2}

    def test_resume_re_decides_a_branch_route(self, tmp_path: Path) -> None:
        run = _run(tmp_path, {"x": 21})
        _fail_once(_routed(), run)

        result = execute_run(_routed(), run, resume=True)

        assert result.outputs["dst"] == 42
        assert _CALLS["dst"] == 2


# ── Workspace layout ─────────────────────────────────────────────────────────


class TestValuesLayout:
    def test_validator_accepts_recorded_values(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        execute_run(_chain(), run)
        assert _value_files(run)
        report = validate_workspace(tmp_path / "ws", errors_only=True)
        assert report.ok, report.violations

    def test_validator_flags_a_stray_in_values(self, tmp_path: Path) -> None:
        run = _run(tmp_path)
        execute_run(_chain(), run)
        (run.values_dir() / "notes.txt").write_text("hi")
        (run.values_dir() / ("a" * 64 + ".json")).mkdir()
        report = validate_workspace(tmp_path / "ws", errors_only=True)
        flagged = {Path(item.path).name for item in report.violations}
        assert {"notes.txt", "a" * 64 + ".json"} <= flagged


def test_compiled_workflow_is_accepted_too(tmp_path: Path) -> None:
    run = _run(tmp_path)
    compiled = (_chain()).compile()
    _fail_once(compiled, run)
    execute_run(compiled, run, rerun=True, only=("b",))
    assert _CALLS == {"a": 1, "b": 2}
