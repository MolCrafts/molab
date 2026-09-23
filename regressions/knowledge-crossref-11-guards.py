"""Public-API goldens for knowledge-crossref-11-guards.

Hard-coded: the law flipped one way. A written document lands at
``knowledges/<slug>.md`` (the six built-ins are *file* items, never a
``knowledges/<slug>/note.json`` directory), every public knowledge name is
defined in ``molab.knowledge``, a workspace run still prunes its own output
subtrees with nothing registered in the concept-type registry, and importing
``molab.workspace`` in a fresh interpreter never pulls ``molab.knowledge`` in.
Uses ``molab.knowledge`` / ``molab.workspace`` only — no third-party runtime.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from molab.knowledge import Knowledge, Note, folder
from molab.knowledge.types import non_concept_subdirs
from molab.workspace.folder import WORKSPACE_RUN_KIND
from molab.workspace.run import Run


def main() -> None:
    # ── every public knowledge name is defined in molab.knowledge ────────────
    assert Note.__module__ == "molab.knowledge.concepts"
    assert Knowledge.__module__ == "molab.knowledge.concept"

    # ── host + name derives one markdown file, and the bytes land there ──────
    with tempfile.TemporaryDirectory() as raw:
        host = Path(raw) / "exp"
        doc = Note(host, "Tg Cooling")

        assert doc.path == host / "knowledges" / "tg-cooling.md"
        assert not doc.exists(), "binding a name must not touch disk"

        doc.write("# Tg Cooling\n\nQuench at 10 K/ns.\n")

        assert (host / "knowledges" / "tg-cooling.md").is_file()
        # A file item, not a directory: the layout marks a document by its .md.
        assert not (host / "knowledges" / "tg-cooling").exists()
        assert folder(host, "Tg Cooling", Note) == host / "knowledges" / "tg-cooling.md"
        assert Knowledge.open(doc.path).name == "tg-cooling"

    # ── the pruning contract survives with nothing registered ────────────────
    assert "executions" in Run.NON_CONCEPT_SUBDIRS
    assert non_concept_subdirs(WORKSPACE_RUN_KIND) == Run.NON_CONCEPT_SUBDIRS

    # ── the one-way law: a bare workspace import never reaches knowledge ─────
    code = (
        "import sys\n"
        "import molab.workspace  # noqa: F401\n"
        "assert 'molab.knowledge' not in sys.modules, sorted(sys.modules)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


if __name__ == "__main__":
    main()
    print("knowledge-crossref-11-guards: ok")
