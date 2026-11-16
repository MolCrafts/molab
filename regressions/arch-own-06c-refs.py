"""arch-own-06c-refs: a harvested run is one molab reference.

Hard-coded: the run reference, the single derived_from line, no ``sources:``
frontmatter, source kinds ``run`` then ``experiment``, ``Workspace.find`` of
that reference, a missing run ref that stays in ``links()``, and ``molab://``
rejected by ``is_ref``. Public API only — no third-party runtime.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from molab.knowledge import Finding, Note
from molab.workspace import RefNotFoundError, Workspace
from molab.workspace.refs import is_ref, ref_of


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        workspace = Workspace(root=Path(raw) / "lab", name="Lab")
        workspace.materialize()
        experiment = workspace.add_project("p").add_experiment("e")
        run = experiment.add_run(params={"x": 1}, id="c0ffee00")
        with run.start() as ctx:
            ctx.mark_succeeded()

        item = Finding.harvest(run, narrative="the run converged", created_by="regression")
        run_ref = f"molab:experiment/{experiment.id}/run/c0ffee00"
        assert str(ref_of(run)) == run_ref
        line = f"- [@derived_from c0ffee00]({run_ref})"
        text = item.path.read_text(encoding="utf-8")
        assert text.count(line) == 1
        assert "sources:" not in text
        assert [source.kind for source in item.sources] == ["run", "experiment"]
        assert workspace.find(item.sources[0].ref).id == "c0ffee00"

        dead = f"molab:experiment/{experiment.id}/run/deadbeef"
        note = Note(workspace, "gone")
        note.write(f"- [gone]({dead})\n")
        assert any(edge.target == dead for edge in note.links())
        try:
            workspace.find(dead)
        except RefNotFoundError as exc:
            assert exc.segment == "run"
        else:
            raise AssertionError("deadbeef resolved")

        assert is_ref("molab://x") is False


if __name__ == "__main__":
    main()
    print("arch-own-06c-refs: ok")
