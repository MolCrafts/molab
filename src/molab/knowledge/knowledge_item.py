"""Typed pointers a knowledge document cites.

:class:`SourceRef` is the value written as a markdown link. A run, experiment,
project or asset is a reference; literature is an https link; a file
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


SourceKind = Literal["project", "experiment", "run", "execution", "asset", "file", "reference"]
"""What a :class:`SourceRef` points at: a ``molab:`` entity (the kinds of
:data:`molab.workspace.refs.RefKind`, which knowledge may not import at module
level), a workspace file, or literature."""


def _reference_url(text: str) -> str | None:
    """*text* as a literature URL: an http(s) URL as is, a DOI as its https form; else ``None``."""
    if text.startswith(("http://", "https://")):
        return text
    if text.upper().startswith("DOI:"):
        return "https://doi.org/" + text.split(":", 1)[1].strip()
    if text.startswith("10."):
        return "https://doi.org/" + text
    return None


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
        span: str | None = None,
    ) -> SourceRef:
        """A source pointing at a live workspace entity.

        Project, Experiment, Run, and Asset become the ``molab:`` reference
        :func:`molab.workspace.refs.ref_of` builds. Any other workspace
        ``Folder`` is a ``file`` source at that folder's absolute path.

        Raises:
            TypeError: *entity* is not a workspace folder or asset.
        """
        from molab.workspace.domain import Asset
        from molab.workspace.experiment import Experiment
        from molab.workspace.folder import Folder
        from molab.workspace.project import Project
        from molab.workspace.refs import ref_of
        from molab.workspace.run import Run

        if isinstance(entity, (Project, Experiment, Run, Asset)):
            built = ref_of(entity)
            return cls(kind=built.kind, ref=str(built), span=span)
        if isinstance(entity, Folder):
            return cls(kind="file", ref=str(entity.resolve()), span=span)
        path = getattr(entity, "path", None)
        if getattr(entity, "FILE_DOCUMENT", False) and path is not None:
            return cls(kind="file", ref=str(path), span=span)
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

        if self.kind in {"project", "experiment", "run", "execution", "asset"}:
            if not is_ref(self.ref):
                raise ValueError(
                    f"entity source {self.ref!r} is not a molab reference; use SourceRef.of"
                )
            target = self.ref
        elif self.kind == "reference":
            url = _reference_url(self.ref)
            if url is None:
                raise ValueError(f"reference {self.ref!r} is not an http(s) URL or a DOI")
            target = url
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
    def parse(cls, text: str, *, span: str | None = None) -> SourceRef:
        """The source one string names.

        A ``molab:`` ref keeps its parsed kind. An http(s) URL or a DOI is a
        ``reference`` (a DOI in its https form). Anything else is a ``file``.

        Raises:
            InvalidRefError: *text* is a malformed ``molab:`` ref.
        """
        from molab.workspace.refs import is_ref, parse_ref

        if is_ref(text):
            return cls(kind=parse_ref(text).kind, ref=text, span=span)
        url = _reference_url(text)
        if url is not None:
            return cls(kind="reference", ref=url, span=span)
        return cls(kind="file", ref=text, span=span)

    @classmethod
    def from_edge(cls, edge: Edge) -> SourceRef:
        """The source a typed edge writes back as: :meth:`parse`, with a ``#fragment`` as *span*."""
        target, sep, fragment = edge.target.partition("#")
        return cls.parse(target, span=fragment if sep else None)

    @classmethod
    def normalize(
        cls,
        sources: list[SourceRef | object] | None,
        *,
        default_host: object,
    ) -> list[SourceRef]:
        """Normalize a free-form source list into typed :class:`SourceRef`\\ s.

        A ``Folder`` becomes :meth:`of`; a string is :meth:`parse`\\ d. An
        empty request is ``[SourceRef.of(default_host)]``.
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
                out.append(cls.parse(str(item)))
        return out


__all__ = [
    "SourceKind",
    "SourceRef",
]
