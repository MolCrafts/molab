"""Public-API goldens for arch-own-03f-results.

Driver results are one reserved Artifact, not a sidecar and not evidence:

1. Workspace ``Lab`` / project ``alpha`` / experiment ``sweep``; one run
   ``params={"seed": 1}``.
2. Inside ``run.start()``: ``emit_artifact`` of ``b'{"user": 1}'`` named
   ``results.json``; a second emit of that name raises ``ValueError``;
   ``set_result`` overwrites ``energy`` (``-1.5`` then ``-2.25``) and sets
   ``converged``; ``ctx.get_result("energy")`` is ``-2.25``.
3. That attempt has exactly one Artifact with ``semantic_type == "result"``:
   name ``results.json``, media type ``application/json``, path ending in
   ``artifacts/_molab/results.json``.
4. ``run.results`` / ``run.get_result`` return those driver values.
   ``ArtifactRepository.read_bytes`` returns the user bytes, whose digest is
   their sha256. Evidence has no ``results`` kind, and
   ``executions/eNN/results.json`` does not exist.
5. A ``RERUN`` attempt that never calls ``set_result`` has ``results == {}``.

The script prints ``arch-own-03f-results: ok`` last and exits 0, or prints the
differences and exits 1.

Provenance: goldens hard-coded from ``.claude/specs/arch-own-03f-results.md``
lines 250-264 and acceptance ac-013 (no third-party oracle), recorded
2026-10-01. In-process temporary directory — no network, no third-party
runtime. ``hashlib`` is stdlib.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile

from molab.workspace import Workspace
from molab.workspace.artifact_repository import ArtifactRepository
from molab.workspace.domain import ExecutionMode

_USER_BYTES = b'{"user": 1}'
_RESULT_PATH_SUFFIX = "artifacts/_molab/results.json"
_RESULTS = {"energy": -2.25, "converged": True}


def main() -> int:
    problems: list[str] = []

    def check(label: str, got: object, expected: object) -> None:
        if got != expected:
            problems.append(f"{label}: got {got!r}, expected {expected!r}")

    with tempfile.TemporaryDirectory() as tmp:
        ws = Workspace(root=tmp, name="Lab")
        ws.materialize()
        run = ws.add_project("alpha").add_experiment("sweep").add_run(params={"seed": 1})

        with run.start() as ctx:
            user = ctx.emit_artifact(_USER_BYTES, name="results.json")
            try:
                ctx.emit_artifact(b"x", name="results.json")
            except ValueError:
                pass
            else:
                problems.append(
                    "second emit_artifact(name='results.json'): "
                    "expected ValueError, no exception raised"
                )
            ctx.set_result("energy", -1.5)
            ctx.set_result("converged", True)
            ctx.set_result("energy", -2.25)
            check("ctx.get_result('energy')", ctx.get_result("energy"), -2.25)
            e1 = ctx.id

        result_artifacts = [
            artifact
            for artifact in run.execution(e1).artifacts
            if artifact.semantic_type == "result"
        ]
        check("result artifact count", len(result_artifacts), 1)
        if len(result_artifacts) == 1:
            result = result_artifacts[0]
            check("result name", result.name, "results.json")
            check("result media_type", result.media_type, "application/json")
            if not result.path.endswith(_RESULT_PATH_SUFFIX):
                problems.append(
                    "result path: got "
                    f"{result.path!r}, expected to end with {_RESULT_PATH_SUFFIX!r}"
                )

        check("run.results(e1)", run.results(e1), _RESULTS)
        check("run.get_result('energy')", run.get_result("energy", execution_id=e1), -2.25)

        repo = ArtifactRepository(ws.root, fs=ws.fs)
        check(
            "read_bytes(user)",
            repo.read_bytes(user, execution_dir=run.execution_dir(e1)),
            _USER_BYTES,
        )
        check(
            "user.content.digest",
            user.content.digest,
            "sha256:" + hashlib.sha256(_USER_BYTES).hexdigest(),
        )

        evidence_kinds = {item.kind for item in run.execution(e1).evidence}
        check("'results' in evidence", "results" in evidence_kinds, False)
        check(
            "execution_dir/results.json exists",
            (run.execution_dir(e1) / "results.json").exists(),
            False,
        )

        with run.start(mode=ExecutionMode.RERUN) as ctx:
            e2 = ctx.id
        check("run.results(e2)", run.results(e2), {})

    if problems:
        for problem in problems:
            print(f"MISMATCH: {problem}")
        return 1
    print("arch-own-03f-results: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
