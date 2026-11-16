"""Public-API goldens for knowledge-crossref-09-sever-types.

Hard-coded: the workspace's Folder type table answers for its four levels and
for nothing else (a fresh process registers exactly four entity filenames), the
six forwarder shells are *absent* (``find_spec`` is ``None``), the knowledge
names they re-exported are unreachable on ``molab.workspace``, the duplicated
markdown-edge machinery is gone while the canonical pair in ``molab.knowledge``
still round-trips a typed edge, and ``molab.knowledge`` declares the four
workspace entity filenames as Concept markers itself. Uses ``molab.workspace`` /
``molab.knowledge`` only — no third-party runtime.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import molab.knowledge  # noqa: F401
import molab.workspace
from molab.knowledge.concept import Concept, append_link, marker_filenames
from molab.workspace.folder import class_for_entity_file, entity_json_names

#: The four levels of the tree, each registered by its own module.
CORE_ENTITY_JSON = ("workspace.json", "project.json", "experiment.json", "run.json")

#: The forwarder shells the workspace shed. ``bundle_index`` outlived this cut
#: (it was still imported by ``workspace_context``) and is deleted by the
#: follow-up member knowledge-crossref-10-sever-reads.
SEVERED_SHELLS = (
    "molab.workspace.edges",
    "molab.workspace.concepts",
    "molab.workspace.concept_meta",
    "molab.workspace.note_meta",
    "molab.workspace.reference_meta",
    "molab.workspace.zotero_concepts",
)


def main() -> None:
    # ── the filename axis holds the four levels, and only what was registered ─
    assert entity_json_names() == CORE_ENTITY_JSON, entity_json_names()
    assert class_for_entity_file("project.json") is molab.workspace.Project
    assert class_for_entity_file("run.json") is molab.workspace.Run
    assert class_for_entity_file("finding.json") is None

    # ── the six shells are gone, and gone for real ───────────────────────────
    for module in SEVERED_SHELLS:
        assert importlib.util.find_spec(module) is None, module
    # ``bundle_index`` was the one shell this cut left standing; 10 removed it.
    assert importlib.util.find_spec("molab.workspace.bundle_index") is None

    # ── knowledge's names left the workspace surface ─────────────────────────
    for name in (
        "Note",
        "Literature",
        "NoteMeta",
        "ReferenceMeta",
        "ZoteroItem",
        "Edge",
        "EdgeRole",
        "DEFAULT_EDGE_ROLE",
        "KnowledgeNotFoundError",
        "ConceptNotFoundError",
    ):
        assert not hasattr(molab.workspace, name), name
    assert not hasattr(molab.workspace.folder, "LinkScan")
    assert not hasattr(molab.workspace.folder, "append_link")
    for method in ("links", "out_edges", "typed_out_edges"):
        assert not hasattr(molab.workspace.Folder, method), method

    # ── …and the host declared them to knowledge instead ─────────────────────
    markers = marker_filenames()
    for name in CORE_ENTITY_JSON:
        assert name in markers, (name, markers)

    # ── the canonical markdown-edge pair still writes and reads an edge ──────
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        src = Concept(root / "src", type="bundle.concept")
        dst = Concept(root / "dst", type="bundle.concept")
        src.write_index("# src\n")
        dst.write_index("# dst\n")

        append_link(src, dst, role="records")

        edges = src.links()
        assert len(edges) == 1, edges
        assert edges[0].role == "records", edges[0].role
        assert edges[0].target == str(dst.path), edges[0].target

    # ── and a workspace still materializes through the public API ────────────
    with tempfile.TemporaryDirectory() as raw:
        workspace = molab.workspace.Workspace(root=Path(raw) / "lab", name="Lab")
        workspace.materialize()
        run = workspace.add_project("p").add_experiment("e").add_run(params={"seed": 42})

        assert Path(str(run.resolve())).name == "seed=42"
        assert workspace.validate().ok is True


if __name__ == "__main__":
    main()
    print("knowledge-crossref-09-sever-types: ok")
