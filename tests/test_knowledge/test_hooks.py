"""The knowledge-side ``knowledge.created`` emitter (``molab.knowledge.hooks``).

The hook is a **single slot**: any module that has imported
``molab.workspace.bundle`` installs the workspace-side emitter instead. So the
identity of the registered callable is what gets pinned — re-executing the
module body proves the self-registration is what installs it — and never merely
the fact that some emitter fired. A raising emitter must still be swallowed: the
Concept is already durable on disk when it runs.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from molab.knowledge import Note


def _knowledge_hooks() -> Any:
    """Re-execute the hooks module body and return the module.

    Re-execution is the point: it re-runs the module-scope
    ``set_concept_created_hook(...)`` call, so ``_HOOK`` is deterministically the
    knowledge-side emitter even in a session where another module installed its
    own.
    """
    return importlib.reload(importlib.import_module("molab.knowledge.hooks"))


class TestKnowledgesOwnEmitter:
    def test_the_module_body_installs_the_knowledge_emitter(self) -> None:
        hooks = _knowledge_hooks()

        assert hooks._HOOK is hooks._emit_knowledge_created

    def test_an_event_records_exactly_one_knowledge_created(
        self, lab: Any, experiment: Any, monkeypatch: Any
    ) -> None:
        hooks = _knowledge_hooks()
        note = Note(experiment, "Tg Cooling")
        note.write("# Tg Cooling\n")
        calls: list[tuple[str, str, str, list[Path]]] = []

        from molab.workspace.history import GitHistory

        def record(self: Any, event: str, *, subject: Any, summary: str, paths: Any) -> None:
            calls.append((event, subject.id, summary, list(paths)))

        monkeypatch.setattr(GitHistory, "record", record)

        hooks.notify_concept_created(root=lab.root, concept=note, title="Tg Cooling")

        assert calls == [
            (
                "knowledge.created",
                Path(note.path).relative_to(lab.root).as_posix(),
                "Tg Cooling",
                [Path(note.path)],
            )
        ]

    def test_a_raising_emitter_is_swallowed(
        self, lab: Any, experiment: Any, monkeypatch: Any
    ) -> None:
        hooks = _knowledge_hooks()
        note = Note(experiment, "Tg Cooling")
        note.write("# Tg Cooling\n")

        from molab.workspace.history import GitHistory

        def boom(self: Any, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("no event spine here")

        monkeypatch.setattr(GitHistory, "record", boom)

        hooks.notify_concept_created(root=lab.root, concept=note, title="Tg Cooling")

        assert note.read() == "# Tg Cooling\n"

    def test_an_absent_hook_emits_nothing(
        self, lab: Any, experiment: Any, monkeypatch: Any
    ) -> None:
        hooks = _knowledge_hooks()
        note = Note(experiment, "Tg Cooling")
        monkeypatch.setattr(hooks, "_HOOK", None)

        hooks.notify_concept_created(root=lab.root, concept=note, title="Tg Cooling")
