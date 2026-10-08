"""arch-own-06e: directory-form knowledge and the retired modules are gone.

Public API only. Hard-coded goldens. No third-party runtime.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path

from molab.knowledge import Knowledge, KnowledgeNotFoundError, Note
from molab.workspace import Workspace

_RETIRED = tuple(
    "molab.knowledge." + name for name in ("bundle", "bundle_index", "types", "hooks", "note_meta")
)


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "ws"
        Workspace(root, name="lab").materialize()

        Note(root, "Tg Cooling").write("# Tg cooling\n\nQuench at 10 K/ns.\n")

        knowledges = root / "knowledges"
        (knowledges / "finding-a.md").write_text(
            "---\nclass: Finding\nsources:\n- kind: file\n  ref: legacy.txt\n---\n\n# A\n",
            encoding="utf-8",
        )
        (knowledges / "finding-b.md").write_text(
            "---\nclass: Finding\n---\n\n# B\n\n- [@derived_from R1](molab:experiment/E1/run/R1)\n",
            encoding="utf-8",
        )
        legacy = knowledges / "old-note"
        legacy.mkdir()
        (legacy / "note.json").write_text("{}\n", encoding="utf-8")
        (legacy / "index.md").write_text("# Old\n\nquench\n", encoding="utf-8")

        opened = Knowledge.open(knowledges / "tg-cooling.md")
        print(f"open: {type(opened).__name__} {opened.type()}")

        hits = Knowledge(root).search("quench").hits
        assert len(hits) == 1
        hit = hits[0]
        print(f"search: {hit.entry.path} | {hit.entry.title}")

        walked = sorted(
            Path(os.path.relpath(doc.path, root)).as_posix() for doc in Knowledge(root).walk()
        )
        print(f"walk: {walked}")

        frontmatter_only = len(Knowledge.open(knowledges / "finding-a.md").sources)
        linked = len(Knowledge.open(knowledges / "finding-b.md").sources)
        print(f"sources: frontmatter-only={frontmatter_only} linked={linked}")

        try:
            Knowledge.open(legacy)
        except KnowledgeNotFoundError:
            print("legacy-dir: KnowledgeNotFoundError")
        else:
            raise AssertionError("a directory opened as a document")

        handle = Knowledge(root)
        raised: list[str] = []
        for verb in ("read", "tags"):
            try:
                getattr(handle, verb)()
            except TypeError:
                raised.append("TypeError")
            else:
                raise AssertionError(verb)
        print(f"root-handle: {' '.join(raised)}")

        importable = sum(importlib.util.find_spec(name) is not None for name in _RETIRED)
        print(f"retired-modules: {importable}/{len(_RETIRED)} importable")

    print("OK")


if __name__ == "__main__":
    main()
