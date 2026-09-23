"""Public-API goldens for knowledge-crossref-02-owner.

Hard-coded: the landed paths ``knowledges/tg-cooling.md`` and
``knowledges/tg-rise.md``, the directory form ``knowledges/records``, the
``@cites`` edge label (written through 01's ``.ref``), the absence of the file
before the first write, and the unchanged single-argument path form. Uses
``molab.knowledge``'s public surface plus a real ``Workspace`` host.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from molab.knowledge import Finding, Knowledge, Note, SourceRef, folder
from molab.workspace import Workspace


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        workspace = Workspace(root=Path(raw) / "lab")
        workspace.materialize()
        experiment = workspace.add_project("p").add_experiment("e")

        knowledges = Path(str(experiment.resolve())) / "knowledges"

        # The one derivation: the class decides the landed form.
        assert folder(experiment, "Tg Cooling", Note) == knowledges / "tg-cooling.md"
        assert folder(experiment, "Tg Rise", Finding) == knowledges / "tg-rise.md"
        assert folder(experiment, "records", Knowledge) == knowledges / "records"

        # Host construction derives path and disk, and writes nothing.
        cooling = Note(experiment, "Tg Cooling")
        rise = Finding(experiment, "Tg Rise", sources=[SourceRef(kind="experiment", ref="exp-1")])
        assert cooling.path == knowledges / "tg-cooling.md"
        assert rise.path == knowledges / "tg-rise.md"
        assert cooling.fs is experiment._disk()
        assert not knowledges.exists(), "construction touched the disk"

        # The first write lands the bytes; .ref appends the hard-coded edge label.
        rise.write("# Tg rises with the cooling rate\n")
        cooling.ref(rise, role="cites")
        assert cooling.path.is_file()
        assert "@cites" in cooling.path.read_text()

        # The host is not retained: the handle is still path-identity.
        twin = Knowledge(folder(experiment, "Tg Cooling", Note))
        assert cooling == twin
        assert hash(cooling) == hash(twin)
        assert not hasattr(cooling, "_host")

        # The single-argument path form is byte-identical to before.
        assert Knowledge("/wiki/cooling").path == Path("/wiki/cooling")
        assert Note("/wiki/cooling").path == Path("/wiki/cooling.md")


if __name__ == "__main__":
    main()
