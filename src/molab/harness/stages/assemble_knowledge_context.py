"""``AssembleKnowledgeContext`` — the plan pipeline's prior-knowledge digest.

Persists the workspace's accumulated knowledge (the six product classes)
as a first-class ``knowledge_context`` artifact the proposal/spec writers
consume — so "which prior knowledge shaped this plan" is an auditable
lineage edge through the gateway's ``parent_ids`` path, never a prompt-side
side-channel.

Selection is **deterministic, no LLM**: ``Knowledge(root).walk()`` yields
the six classes, ordered Report → Finding → Plan → Observation → Note →
Literature then path. Every cap states what it omitted (no silent caps),
and an empty workspace still persists a digest saying so.

The stage locates the owning workspace by walking up from
``ctx.workspace_root`` (a plan run's ctx roots at the *run dir*) to the
nearest ``workspace.json``; a run mounted outside any workspace yields the
honest "not inside a workspace" digest.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from molab.harness.core.run_context import HarnessRunContext
from molab.harness.core.stage import Stage
from molab.harness.schemas import PlanArtifactRef
from molab.knowledge import Finding, Knowledge, Literature, Note, Observation, Plan, Report

if TYPE_CHECKING:
    pass

__all__ = ["AssembleKnowledgeContext"]

MAX_ITEMS = 12
"""Knowledge bodies included in one digest."""

MAX_BODY_CHARS = 1200
"""Per-item body excerpt length."""

MAX_TOTAL_CHARS = 16_000
"""Whole-digest hard cap."""

_CLASS_ORDER: tuple[type, ...] = (Report, Finding, Plan, Observation, Note, Literature)

_TS_FLOOR = datetime(1970, 1, 1, tzinfo=UTC)

_EMPTY_DIGEST = "no prior knowledge recorded in this workspace"
_NO_WORKSPACE_DIGEST = "no prior knowledge available (run is not mounted inside a workspace)"


def _find_workspace_root(start: Path) -> Path | None:
    """Walk up from *start* to the nearest dir holding ``workspace.json``."""
    for candidate in (start, *start.parents):
        if (candidate / "workspace.json").is_file():
            return candidate
    return None


class AssembleKnowledgeContext(Stage):
    """Digest the workspace's prior knowledge into one plan artifact."""

    name: ClassVar[str] = "assemble_knowledge_context"

    async def run(self, ctx: HarnessRunContext) -> PlanArtifactRef:
        digest = self._render_digest(Path(ctx.workspace_root))
        return ctx.artifact_store.put_text(
            kind="knowledge_context",
            text=digest,
            created_by=self.name,
            parent_ids=[],
        )

    def _render_digest(self, start: Path) -> str:
        from molab.knowledge import Knowledge
        from molab.knowledge.bundle_index import extract_title

        root = _find_workspace_root(start)
        if root is None:
            return _NO_WORKSPACE_DIGEST
        walked = list(Knowledge(root).walk())
        if not walked:
            return _EMPTY_DIGEST

        def _prio(item: object) -> int:
            try:
                return _CLASS_ORDER.index(type(item))  # type: ignore[arg-type]
            except ValueError:
                return len(_CLASS_ORDER)

        walked.sort(key=lambda item: (_prio(item), str(item.path)))
        lines = ["# Prior knowledge (workspace digest)", ""]
        for concept in walked[:MAX_ITEMS]:
            title = extract_title(concept.read()) or concept.name
            rel = str(Path(concept.path).relative_to(root))
            body = self._body(concept)
            lines.append(f"## [{type(concept).__name__}] {title}")
            lines.append(f"path: {rel}")
            if body:
                lines.append(body)
            lines.append("")
        if len(walked) > MAX_ITEMS:
            lines.append(f"(+{len(walked) - MAX_ITEMS} more knowledge items not shown)")
        digest = "\n".join(lines).strip()
        if len(digest) > MAX_TOTAL_CHARS:
            digest = digest[:MAX_TOTAL_CHARS] + "\n... (digest truncated at the total cap)"
        return digest or _EMPTY_DIGEST

    @staticmethod
    def _timestamp(meta: Mapping[str, object]) -> datetime:
        raw = meta.get("timestamp")
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
        if isinstance(raw, str):
            try:
                parsed = datetime.fromisoformat(raw)
            except ValueError:
                return _TS_FLOOR
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        return _TS_FLOOR

    @staticmethod
    def _body(concept: Knowledge) -> str:
        body = (concept.read() or "").strip()
        if len(body) > MAX_BODY_CHARS:
            return body[:MAX_BODY_CHARS] + f"\n... (+{len(body) - MAX_BODY_CHARS} chars omitted)"
        return body
