"""Public-API goldens for knowledge-crossref-01-ref.

Hard-coded: the appended markdown line
``- [@derived_from smith2024](smith2024.md)`` and the edge roles. The one
integration case in this spec — a real workspace ``Folder`` is only ever
rejected here, never in the knowledge-owned unit tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from molab.knowledge import Knowledge, Literature, Note
from molab.workspace.folder import Folder


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        idea = Note(root / "idea")
        smith = Literature(root / "smith2024")
        smith.write("Smith et al. 2024\n")

        # The object form, and the hard-coded golden line it appends.
        idea.ref(smith, text="smith2024", role="derived_from")
        text = (root / "idea.md").read_text()
        assert text.endswith("- [@derived_from smith2024](smith2024.md)\n"), text
        assert idea.links() == [(str(smith.path), "derived_from")]

        # The path form: a Knowledge read back off disk is what a caller holds,
        # and its .path is what .ref must accept.
        opened = Knowledge.open(smith.path)
        assert type(opened) is Literature
        review = Note(root / "review")
        review.ref(opened.path, role="cites")
        assert review.links() == [(str(smith.path), "cites")]

        # Nothing outside the Knowledge family is a cross-reference target.
        folder = Folder(name="lab", kind="workspace.root", root_path=root)
        for rejected in (folder, 42, "projects/p/experiments/e"):
            try:
                idea.ref(rejected)
            except TypeError:
                pass
            else:
                raise AssertionError(f".ref accepted {rejected!r}")

        assert (root / "idea.md").read_text() == text


if __name__ == "__main__":
    main()
