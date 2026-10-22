"""List a run's generated image parts and write them as a viewable Report.

``Finding.harvest`` records what a run *means* as text. It does not show the
images the run emitted. :class:`GeneratedParts` lists those images and writes
a Report whose body both cites each artifact (``[@records](molab:...)``) and
embeds the file (a relative ``![]()``), so a plain markdown preview shows the
picture. A ``molab:`` URL is not an image a previewer can fetch.

A task cannot call this. ``TaskContext`` has no path up to the Run.
After ``molab run``, ``molab knowledge parts --write`` stores the Report.
"""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from molab.ids import slugify

from .concepts import Report
from .edges import encode_label, link_line
from .knowledge_item import SourceRef, _relative_posix

if TYPE_CHECKING:
    from molab.workspace.domain import Artifact, Execution
    from molab.workspace.run import Run

__all__ = ["GeneratedPart", "GeneratedParts"]

_SKIP_SEMANTIC_TYPES = frozenset({"result", "checkpoint"})


class GeneratedPart(NamedTuple):
    """One image (or explicitly tagged part) emitted by a run.

    Attributes:
        name: Artifact name, such as ``hair.png``.
        part: ``metadata["tags"]["part"]`` when that tag is a non-empty
            string, otherwise the artifact name's stem.
        artifact_id: Artifact id.
        execution_id: Attempt that emitted it.
        ref: ``molab:experiment/.../run/.../artifact/...``.
        path: Absolute path of the artifact bytes.
        media_type: Recorded media type, if any.
    """

    name: str
    part: str
    artifact_id: str
    execution_id: str
    ref: str
    path: str
    media_type: str | None


class GeneratedParts:
    """The image parts one run emitted.

    ``GeneratedParts(run).list()`` reads one attempt.
    ``GeneratedParts(run).view(...)`` writes the Report.
    """

    def __init__(self, run: Run) -> None:
        """Bind the run whose image parts this object lists and views."""
        self._run = run

    def list(
        self,
        *,
        execution_id: str | None = None,
    ) -> builtins.list[GeneratedPart]:
        """Image artifacts of one attempt, ordered by artifact name.

        An artifact is included when its media type starts with ``image/``, or
        when its tags carry a ``part`` key. ``semantic_type`` ``result`` and
        ``checkpoint`` are skipped. The latest attempt is used when
        *execution_id* is omitted.

        Raises:
            ValueError: The run has no attempt, or *execution_id* is unknown.
        """
        run = self._run
        execution = _execution(run, execution_id)
        found: list[GeneratedPart] = []
        for artifact in execution.artifacts:
            if not _is_part(artifact):
                continue
            location = run.artifact_location(execution.id, artifact)
            found.append(
                GeneratedPart(
                    name=artifact.name,
                    part=_part_label(artifact),
                    artifact_id=artifact.id,
                    execution_id=execution.id,
                    ref=str(SourceRef.of(run, artifact_id=artifact.id).ref),
                    path=str(Path(location).resolve()),
                    media_type=artifact.media_type,
                )
            )
        found.sort(key=lambda item: item.name)
        return found

    def view(
        self,
        *,
        narrative: str,
        created_by: str,
        name: str | None = None,
        execution_id: str | None = None,
    ) -> Report:
        """Write a Report under the run's experiment that shows its image parts.

        Same preconditions as harvest: the run is terminal, and *narrative* is
        non-empty. Re-writing the same *name* replaces the body.

        Each part is a ``records`` link to its ``molab:`` artifact ref, plus a
        relative image when the bytes are an image. The image path is computed
        from the document's directory before the file is written.

        Raises:
            ValueError: The run is not terminal, *narrative* is blank, or the
                attempt cannot be resolved.
        """
        from molab.workspace.run import TERMINAL_STATUSES

        from .write import write_knowledge

        run = self._run
        status = run.status_label
        if status not in TERMINAL_STATUSES:
            raise ValueError(
                f"run {run.id} is {status!r} — only a terminal run "
                f"({sorted(TERMINAL_STATUSES)}) has parts to view"
            )
        if not narrative.strip():
            raise ValueError(
                "GeneratedParts.view requires a non-empty narrative — knowledge is "
                "interpretation; the raw record already lives in run.json and the "
                "run's artifacts"
            )

        parts = self.list(execution_id=execution_id)
        experiment = run.experiment
        item_name = name or f"parts-{slugify(run.id) or run.id}"
        sources = [SourceRef.of(run), SourceRef.of(experiment)]
        doc_path = Report(
            experiment,  # ty: ignore[invalid-argument-type]
            item_name,
            sources=sources,
        ).path
        body = _render_body(narrative, parts, base_dir=str(doc_path.parent))
        written = write_knowledge(
            experiment,
            name=item_name,
            of=Report,
            sources=sources,
            created_by=created_by,
            text=body,
            title=item_name,
        )
        if not isinstance(written, Report):
            raise TypeError(f"GeneratedParts.view wrote {type(written).__name__}, expected Report")
        return written


def _execution(run: Run, execution_id: str | None) -> Execution:
    """The named attempt, or the latest one."""
    if execution_id is None:
        executions = run.executions
        if not executions:
            raise ValueError(f"run {run.id} has no execution")
        return executions[-1]
    try:
        return run.execution(execution_id)
    except KeyError as exc:
        raise ValueError(f"run {run.id} has no execution {execution_id!r}") from exc


def _is_part(artifact: Artifact) -> bool:
    if artifact.semantic_type in _SKIP_SEMANTIC_TYPES:
        return False
    media = artifact.media_type or ""
    if media.startswith("image/"):
        return True
    tags = artifact.metadata.get("tags")
    return isinstance(tags, dict) and "part" in tags


def _part_label(artifact: Artifact) -> str:
    tags = artifact.metadata.get("tags")
    if isinstance(tags, dict):
        part = tags.get("part")
        if isinstance(part, str) and part.strip():
            return part.strip()
    return Path(artifact.name).stem


def _render_body(narrative: str, parts: list[GeneratedPart], *, base_dir: str) -> str:
    lines = ["# Generated parts", "", narrative.strip(), ""]
    if not parts:
        lines += ["No image parts were emitted.", ""]
        return "\n".join(lines)
    lines += ["## Parts", ""]
    for part in parts:
        lines.append(f"### {part.part}")
        lines.append("")
        lines.append(link_line(encode_label("records", part.part), part.ref))
        lines.append("")
        if part.media_type and part.media_type.startswith("image/"):
            relative = _relative_posix(part.path, base_dir)
            lines.append(f"![{part.part}]({relative})")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
