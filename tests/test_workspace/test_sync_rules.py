"""Sync-rule presets, path containment, and one transfer at a time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from molab.workspace.sync_rules import (
    SyncBusyError,
    SyncFailedError,
    TransferPlan,
    exclusive_transfer,
    execute_rule,
    interval_due,
    load_rules,
    make_rule,
    relativize,
    resolve_under_root,
    transfer_plan,
    upsert_rule,
)


def _rule(**overrides: object):
    fields = {
        "path": "experiments/nve",
        "kind": "directory",
        "direction": "pull",
        "content": "everything",
        "types": (),
        "extra_files": "keep",
        "when": "manual",
        "interval_minutes": 15,
    }
    fields.update(overrides)
    return make_rule(**fields)  # type: ignore[arg-type]


def test_records_code_and_selected_types_include_directories_before_globs() -> None:
    records = transfer_plan(_rule(content="records"))
    assert records == TransferPlan(
        ("*/", "*.json", "*.md", "*.txt", "*.yaml", "*.yml"),
        ("*",),
        False,
        True,
    )
    code = transfer_plan(_rule(content="code"))
    assert code.include == ("*/", "*.py", "workflow.ir.json")
    assert code.exclude == ("*",)
    selected = transfer_plan(_rule(content="types", types=["logs", "py"]))
    assert selected.include == ("*/", "*.py", "*.log", "*.out", "*.err")
    assert selected.exclude == ("*",)


def test_skip_bulk_excludes_products_and_remove_deletes_only_for_folders() -> None:
    plan = transfer_plan(_rule(content="skip-bulk", extra_files="remove"))
    assert plan.include == ()
    assert plan.delete is True
    assert "out/" in plan.exclude
    assert "checkpoints/" in plan.exclude
    assert "*.dcd" in plan.exclude
    file_rule = _rule(path="note.md", kind="file", content="records", extra_files="remove")
    assert transfer_plan(file_rule) == TransferPlan((), (), False, False)
    assert file_rule.content == "everything"
    assert file_rule.extra_files == "keep"


def test_selected_types_reject_an_empty_or_unknown_choice() -> None:
    with pytest.raises(ValueError, match="at least one"):
        _rule(content="types", types=[])
    with pytest.raises(ValueError, match="unknown file type"):
        _rule(content="types", types=["exe"])


def test_relative_paths_cannot_leave_the_root() -> None:
    root = "/lab/nve"
    assert relativize(root, "experiments/a") == "experiments/a"
    assert relativize(root, "/lab/nve/experiments/a") == "experiments/a"
    assert relativize(root, "/lab/nve") == ""
    assert relativize(root, ".") == ""
    assert resolve_under_root(root, "experiments/a") == "/lab/nve/experiments/a"
    assert resolve_under_root(root, "") == "/lab/nve"
    for escaped in (
        "../secret",
        "experiments/../../etc",
        "/etc/passwd",
        "/lab/nve-other/a",
        "a\\b",
    ):
        with pytest.raises(ValueError):
            relativize(root, escaped)


def test_one_rule_per_path_keeps_its_id_and_interval_minimum(tmp_path) -> None:
    mirror = tmp_path / "mirror"
    first = upsert_rule(mirror, path="note.md", kind="file", direction="pull")
    other = upsert_rule(mirror, path="other.md", kind="file", direction="pull")
    again = upsert_rule(mirror, path="note.md", kind="file", direction="push")
    assert again.id == first.id
    assert again.direction == "push"
    assert again.last_run_at is None
    assert other.id != first.id
    assert {rule.path for rule in load_rules(mirror)} == {"note.md", "other.md"}
    with pytest.raises(ValueError, match="at least 5"):
        upsert_rule(
            mirror,
            path="experiments",
            kind="directory",
            when="interval",
            interval_minutes=4,
        )
    with pytest.raises(ValueError, match="relative"):
        upsert_rule(mirror, path="/etc/passwd", kind="file")


def test_upsert_relativizes_only_through_the_caller(tmp_path) -> None:
    """Stored paths are relative. ``..`` never becomes a stored path."""
    mirror = tmp_path / "mirror"
    saved = upsert_rule(mirror, path="experiments/nve", kind="directory", extra_files="remove")
    assert saved.path == "experiments/nve"
    assert saved.extra_files == "remove"
    disk = (mirror / "sync-rules.json").read_text(encoding="utf-8")
    assert "extraFiles" in disk
    assert "--delete" not in disk


def test_preview_does_not_record_a_run_and_a_failure_does(tmp_path) -> None:
    mirror = tmp_path / "mirror"

    class Fake:
        mirror_root = mirror

        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def rsync(self, remote: str, **kwargs: object) -> dict[str, str]:
            self.calls.append({"remote": remote, **kwargs})
            if kwargs.get("direction") == "push":
                raise OSError("remote refused")
            return {"output": "note.md\nexperiments/a.json\n"}

    fs = Fake()
    rule = upsert_rule(mirror, path="experiments", kind="directory", content="records")
    preview = execute_rule(fs, "/lab/nve", rule.id, dry_run=True)
    assert preview.dry_run is True
    assert "experiments/a.json" in preview.output
    assert load_rules(mirror)[0].last_run_at is None
    assert fs.calls[0]["remote"] == "/lab/nve/experiments"
    assert fs.calls[0]["recursive"] is True
    assert fs.calls[0]["include"] == ("*/", "*.json", "*.md", "*.txt", "*.yaml", "*.yml")

    pushed = upsert_rule(mirror, path="experiments", kind="directory", direction="push")
    with pytest.raises(SyncFailedError, match="remote refused"):
        execute_rule(fs, "/lab/nve", pushed.id, dry_run=False)
    failed = load_rules(mirror)
    recorded = next(item for item in failed if item.id == pushed.id)
    assert recorded.last_status == "error"
    assert recorded.last_output == "remote refused"
    assert recorded.direction == "push"


def test_a_second_transfer_does_not_start(tmp_path) -> None:
    mirror = tmp_path / "mirror"

    class Fake:
        mirror_root = mirror

        def rsync(self, remote: str, **kwargs: object) -> dict[str, str]:
            return {"output": "ok"}

    rule = upsert_rule(mirror, path="note.md", kind="file")
    with exclusive_transfer(mirror), pytest.raises(SyncBusyError):
        execute_rule(Fake(), "/lab/nve", rule.id, dry_run=False)
    ran = execute_rule(Fake(), "/lab/nve", rule.id, dry_run=False)
    assert ran.rule.last_status == "ok"


def test_interval_is_due_from_the_last_run() -> None:
    rule = _rule(when="interval", interval_minutes=15)
    now = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    assert interval_due(rule, now) is True
    stamped = rule.__class__(
        **{**rule.__dict__, "last_run_at": (now - timedelta(minutes=14)).isoformat()}
    )
    assert interval_due(stamped, now) is False
    ready = rule.__class__(
        **{**rule.__dict__, "last_run_at": (now - timedelta(minutes=15)).isoformat()}
    )
    assert interval_due(ready, now) is True
