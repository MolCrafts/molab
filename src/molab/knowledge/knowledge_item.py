"""Typed pointers a knowledge document cites.

:class:`SourceRef` is the value written as a markdown link. A run, experiment,
project, artifact or asset is a reference; literature is an https link; a file
is a relative path.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel

from .edges import Edge


def _relative_posix(path: str, base: str) -> str:
    """*path* relative to *base*, including ``..`` segments, as posix."""
    dest = Path(path).parts
    start = Path(base).parts
    common = 0
    for left, right in zip(dest, start, strict=False):
        if left != right:
            break
        common += 1
    ups = ("..",) * (len(start) - common)
    return PurePosixPath(*ups, *dest[common:]).as_posix()


SourceKind = Literal[
    "artifact",
    "run",
    "experiment",
    "project",
    "execution",
    "asset",
    "file",
    "decision",
    "agent_action",
    "reference",
]
"""The kind of canonical object a :class:`SourceRef` points at."""


class SourceRef(BaseModel, frozen=True):
    """A typed pointer to an existing canonical object a document derives from.

    Attributes:
        kind: What sort of object *ref* names.
        ref: The identifier — a content hash, ``run_id``, path, proposal id, or
            reference id, per *kind*.
        span: An optional sub-location (line range / cell / figure region).
    """

    kind: SourceKind
    ref: str
    span: str | None = None

    @classmethod
    def of(
        cls,
        entity: object,
        *,
        artifact_id: str | None = None,
        span: str | None = None,
    ) -> SourceRef:
        """A source pointing at a live workspace entity.

        Project, Experiment, Run, Asset, and a Run plus *artifact_id* become
        the ``molab:`` reference :func:`molab.workspace.refs.ref_of` builds.
        Any other workspace ``Folder`` is a ``file`` source at that folder's
        absolute path.

        Raises:
            TypeError: *entity* is not a workspace folder or asset, or
                *artifact_id* is set on a non-Run.
        """
        from molab.workspace.domain import Asset
        from molab.workspace.experiment import Experiment
        from molab.workspace.folder import Folder
        from molab.workspace.project import Project
        from molab.workspace.refs import ref_of
        from molab.workspace.run import Run

        if isinstance(entity, (Project, Experiment, Run, Asset)):
            built = ref_of(entity, artifact_id=artifact_id)
            return cls(kind=built.kind, ref=str(built), span=span)
        if artifact_id is not None:
            raise TypeError(f"artifact_id is only valid on a Run, got {type(entity).__name__}")
        if isinstance(entity, Folder):
            return cls(kind="file", ref=str(entity.resolve()), span=span)
        raise TypeError(f"SourceRef.of cannot name a {type(entity).__name__}")

    @property
    def link_role(self) -> str:
        """``cites`` for a literature reference; ``derived_from`` otherwise."""
        return "cites" if self.kind == "reference" else "derived_from"

    def link_target(self, base_dir: str) -> str:
        """The markdown target this source writes, relative to *base_dir*.

        Entity kinds require a ``molab:`` ref (build one with :meth:`of`).
        A literature DOI becomes an https DOI URL. A file path that is
        absolute is rewritten relative to *base_dir*.

        Raises:
            ValueError: An entity kind is not a ``molab:`` ref, or a reference
                is neither an http(s) URL nor a DOI.
        """
        from molab.workspace.refs import is_ref

        if self.kind in {"project", "experiment", "run", "execution", "artifact", "asset"}:
            if not is_ref(self.ref):
                raise ValueError(
                    f"entity source {self.ref!r} is not a molab reference; use SourceRef.of"
                )
            target = self.ref
        elif self.kind == "reference":
            text = self.ref
            if text.startswith(("http://", "https://")):
                target = text
            elif text.upper().startswith("DOI:"):
                target = "https://doi.org/" + text.split(":", 1)[1]
            elif text.startswith("10."):
                target = "https://doi.org/" + text
            else:
                raise ValueError(f"reference {text!r} is not an http(s) URL or a DOI")
        else:
            if Path(self.ref).is_absolute():
                target = _relative_posix(self.ref, base_dir)
            else:
                target = self.ref
        if self.span:
            return f"{target}#{self.span}"
        return target

    def link_line(self, base_dir: str) -> str:
        """The one source-link line, rendered by :func:`edges.link_line`."""
        from .edges import encode_label, link_line

        target = self.link_target(base_dir)
        leaf = target.split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
        role = "cites" if self.link_role == "cites" else "derived_from"
        return link_line(encode_label(role, leaf), target)

    @classmethod
    def from_edge(cls, edge: Edge) -> SourceRef:
        """The source a typed edge writes back as.

        A ``molab:`` target keeps its parsed kind. An https target is a
        reference. Anything else is a file at the absolute path. A ``#fragment``
        becomes *span*. A malformed ref raises :class:`InvalidRefError`.
        """
        from molab.workspace.refs import is_ref, parse_ref

        raw = edge.target
        target, sep, fragment = raw.partition("#")
        span = fragment if sep else None
        if is_ref(target):
            parsed = parse_ref(target)
            return cls(kind=parsed.kind, ref=target, span=span)
        if target.startswith(("http://", "https://")):
            return cls(kind="reference", ref=target, span=span)
        return cls(kind="file", ref=target, span=span)

    @classmethod
    def normalize(
        cls,
        sources: list[SourceRef | object] | None,
        *,
        default_host: object,
    ) -> list[SourceRef]:
        """Normalize a free-form source list into typed :class:`SourceRef`\\ s.

        A ``Folder`` becomes :meth:`of`. An empty request is
        ``[SourceRef.of(default_host)]``. A DOI string becomes an https DOI
        reference. Any other string is a ``file`` source.
        """
        from molab.workspace.folder import Folder

        if not sources:
            return [cls.of(default_host)]
        out: list[SourceRef] = []
        for item in sources:
            if isinstance(item, SourceRef):
                out.append(item)
            elif isinstance(item, Folder):
                out.append(cls.of(item))
            else:
                text = str(item)
                if text.upper().startswith("DOI:"):
                    doi = "https://doi.org/" + text.split(":", 1)[1]
                    out.append(cls(kind="reference", ref=doi))
                elif text.startswith("10."):
                    out.append(cls(kind="reference", ref="https://doi.org/" + text))
                else:
                    out.append(cls(kind="file", ref=text))
        return out


__all__ = [
    "SourceKind",
    "SourceRef",
]
