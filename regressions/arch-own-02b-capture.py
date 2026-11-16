"""Public-API goldens for arch-own-02b-capture.

An attempt captures the exact workflow source it was created from, into its
own ``executions/eNN/source/``; a run finds-or-creates by definition hash:

1. ``source_manifest(raw/src/entry.py)`` describes the entrypoint plus its
   first-party import closure (``helper.py``; ``json`` is stdlib and has no
   sibling file) without writing anything. The sources sit outside any git
   repository (``GIT_CEILING_DIRECTORIES``), so the VCS state is unknown.
2. ``run.create_execution(source_entrypoint=...)`` allocates a QUEUED ``e01``
   whose record carries the manifest, and copies the files into
   ``executions/e01/source/``; every copy digests to its manifest sha256.
3. Nothing is written to a run-level ``runs/<slug>/source/``.
4. ``validate_workspace`` reports no ``layout.stray`` (``source`` is a
   declared execution directory) and no error.
5. ``resolve_execution_dir("source")`` is versioned and holds no products.
6. ``experiment.ensure_run`` returns the same run for the same definition, a
   different one for a different ``config_hash``, and ids are UUIDv7.
7. ``compute_run_definition_hash`` without a ``config_hash`` still yields the
   pre-02b digest (``LEGACY_HASH``).

Expected stdout (exactly these lines, exit code 0):

    manifest entry.py ['entry.py', 'helper.py']
    vcs None None
    execution e01 queued ['entry.py', 'helper.py']
    verified True
    run_level_source False
    layout_ok True
    source_dir True False
    ensure_run True True True
    legacy_hash True
    arch-own-02b-capture: ok

Provenance: goldens hard-coded from molab's own behaviour (no third-party
oracle), recorded 2026-09-26 on branch feat/knowledge-crossref. The workspace
is an in-process temporary directory — no network, no third-party runtime.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

from molab.ids import compute_content_hash
from molab.workspace import Workspace
from molab.workspace.execution_dirs import resolve_execution_dir
from molab.workspace.run import compute_run_definition_hash
from molab.workspace.source_snapshot import source_manifest
from molab.workspace.validate import validate_workspace

# Captured at HEAD 56d5b466: the sha256 of the canonical JSON of the run
# definition compute_run_definition_hash(experiment_revision_id="r",
# parameters={"a": 1}) before config_hash existed. Shared with
# tests/test_workspace/test_run_identity.py (LEGACY).
LEGACY_HASH = "sha256:f02450eb8f8c17af093bd72ea04ce070cd69a35593a892293d2538c2d3bbd00b"

_UUID7_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

_GOLDEN = (
    "manifest entry.py ['entry.py', 'helper.py']",
    "vcs None None",
    "execution e01 queued ['entry.py', 'helper.py']",
    "verified True",
    "run_level_source False",
    "layout_ok True",
    "source_dir True False",
    "ensure_run True True True",
    "legacy_hash True",
)


def _emit(lines: list[str], line: str) -> None:
    expected = _GOLDEN[len(lines)]
    assert line == expected, f"{line!r} != {expected!r}"
    lines.append(line)
    print(line)


def _check(raw: Path) -> None:
    lines: list[str] = []
    src = raw / "src"
    src.mkdir()
    entry = src / "entry.py"
    entry.write_text("import helper\nimport json\n")
    (src / "helper.py").write_text("VALUE = 1\n")

    manifest = source_manifest(entry)
    names = [f.name for f in manifest.files]
    _emit(lines, f"manifest {manifest.entrypoint} {names}")
    _emit(lines, f"vcs {manifest.vcs_commit} {manifest.vcs_dirty}")

    ws = Workspace(root=raw / "lab", name="Lab")
    experiment = ws.add_project("p").add_experiment("e")
    run = experiment.add_run(params={"seed": 1})
    ex = run.create_execution(source_entrypoint=entry)
    assert ex.source is not None, ex
    captured = [f.name for f in ex.source.files]
    _emit(lines, f"execution {ex.id} {ex.status.value} {captured}")

    source_dir = Path(run.run_dir) / "executions" / ex.id / "source"
    verified = all(
        (source_dir / f.name).is_file() and compute_content_hash(source_dir / f.name) == f.sha256
        for f in ex.source.files
    )
    _emit(lines, f"verified {verified}")
    _emit(lines, f"run_level_source {(Path(run.run_dir) / 'source').exists()}")

    report = validate_workspace(ws)
    for violation in report.violations:
        print(f"violation: {violation.rule} {violation.path} {violation.detail}", file=sys.stderr)
    strays = [v for v in report.violations if v.rule == "layout.stray"]
    _emit(lines, f"layout_ok {not strays and report.ok}")

    declared = resolve_execution_dir("source")
    _emit(lines, f"source_dir {declared.versioned} {declared.products}")

    first = experiment.ensure_run({"a": 1}, config_hash="h")
    again = experiment.ensure_run({"a": 1}, config_hash="h")
    other = experiment.ensure_run({"a": 1}, config_hash="h2")
    print(f"ensure_run ids: {first.id} {again.id} {other.id}", file=sys.stderr)
    same = first.id == again.id
    different = other.id != first.id
    uuid7 = all(_UUID7_RE.match(r.id) is not None for r in (first, other))
    _emit(lines, f"ensure_run {same} {different} {uuid7}")

    legacy = compute_run_definition_hash(experiment_revision_id="r", parameters={"a": 1})
    print(f"legacy hash: {legacy}", file=sys.stderr)
    _emit(lines, f"legacy_hash {legacy == LEGACY_HASH}")

    assert len(lines) == len(_GOLDEN), lines
    print("arch-own-02b-capture: ok")


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        os.environ["GIT_CEILING_DIRECTORIES"] = raw
        _check(Path(raw))


if __name__ == "__main__":
    main()
