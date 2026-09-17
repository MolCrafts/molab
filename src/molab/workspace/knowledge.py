"""``Knowledge`` — WPER-aligned Folder family for sourced knowledge.

A Knowledge directory lives at ``<project|experiment>/knowledges/<id>/``.
The **class** is the discriminator (via reflection on the entity filename):
``Plan`` → ``plan.json``, ``Finding`` → ``finding.json``. There is no
``type`` field and no ``kind`` field on disk — both were string copies of
the class name.

``project.knowledge(name)`` / ``experiment.knowledge(name)`` are the getters,
same spelling as ``project.experiment(name)``. Narrative is ``index.md``.
No ``meta.json``.

Plan Mode writes a :class:`Plan` named :data:`PLAN_BOOK_NAME` into this
store. Harness plugin state stays at ``run_dir/plan/task_board.json``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import ClassVar, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from molab.path import Path

from .base import _load_metadata, _reconstruct, _save_metadata
from .edges import DEFAULT_EDGE_ROLE, EdgeRole
from .errors import KnowledgeExistsError, KnowledgeNotFoundError
from .folder import (
    Folder,
    append_link,
    class_for_entity_file,
    entity_filename,
    register_entity_class,
)
from .fs import FileSystem, PathArg
from .models import FolderMetadata

KNOWLEDGE_CONTAINER = "knowledges"
PLAN_BOOK_NAME = "plan-book"
KNOWLEDGE_INDEX_FILENAME = "knowledges.json"

SourceKind = Literal[
    "artifact",
    "run",
    "experiment",
    "file",
    "decision",
    "agent_action",
    "reference",
]


class SourceRef(BaseModel, frozen=True):
    """A typed pointer to an existing object this Knowledge derives from."""

    kind: SourceKind
    ref: str
    span: str | None = None


class KnowledgeMetadata(BaseModel, frozen=True):
    """Entity payload of ``plan.json`` / ``finding.json`` / … — no ``type``, no ``kind``."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str
    name: str
    sources: list[SourceRef]
    status: Literal["active", "stale", "superseded", "conflicting"] = "active"
    supersedes: tuple[str, ...] = ()
    confidence: float | None = None
    created_by: str
    created_at: datetime = Field(default_factory=datetime.now)

    @field_validator("sources")
    @classmethod
    def _require_at_least_one_source(cls, value: list[SourceRef]) -> list[SourceRef]:
        if not value:
            raise ValueError(
                "Knowledge must carry at least one SourceRef — source attribution is required"
            )
        return value


@register_entity_class
class Knowledge(Folder):
    """Sourced knowledge Folder. Subclasses are the category (Plan, Finding, …)."""

    _exists_error_cls = KnowledgeExistsError
    _not_found_error_cls = KnowledgeNotFoundError
    DEFAULT_KIND: ClassVar[str] = "knowledge"

    def __init__(
        self,
        *,
        parent: Folder | None = None,
        name: str,
        sources: list[SourceRef] | None = None,
        created_by: str = "user",
        status: Literal["active", "stale", "superseded", "conflicting"] = "active",
        confidence: float | None = None,
        root_path: PathArg | None = None,
        fs: FileSystem | None = None,
        _entity_metadata: KnowledgeMetadata | None = None,
    ) -> None:
        if parent is None and _entity_metadata is None:
            raise ValueError("Knowledge: parent is required")
        kind = entity_filename(type(self)).removesuffix(".json")
        super().__init__(
            parent=parent,
            name=name,
            kind=kind,
            root_path=root_path,
            fs=fs,
        )
        self._entity_metadata = _entity_metadata or KnowledgeMetadata(
            id=self._name,
            name=name,
            sources=list(sources or ()),
            created_by=created_by,
            status=status,
            confidence=confidence,
        )

    def resolve(self) -> Path:
        if self._parent is None:
            return super().resolve()
        return type(self).child_dir(self._parent, self._name)

    @classmethod
    def child_dir(cls, parent: Folder, derived_id: str) -> Path:
        return Path(parent._disk().join(parent.resolve(), KNOWLEDGE_CONTAINER, derived_id))

    @classmethod
    def _index_filename(cls) -> str:
        return KNOWLEDGE_INDEX_FILENAME

    @classmethod
    def from_disk(cls, child_dir: PathArg, parent: Folder) -> Knowledge:
        fs = parent._disk()
        if cls is Knowledge:
            try:
                names = fs.listdir(child_dir)
            except OSError:
                names = []
            for name in names:
                mapped = class_for_entity_file(name)
                if mapped is not None and mapped is not Knowledge and issubclass(mapped, Knowledge):
                    return mapped.from_disk(child_dir, parent)
        path = fs.join(child_dir, entity_filename(cls))
        meta = _load_metadata(KnowledgeMetadata, path, fs=fs)
        folder_meta = FolderMetadata(
            id=meta.id,
            name=meta.name,
            kind=entity_filename(cls).removesuffix(".json"),
            created_at=meta.created_at,
            updated_at=meta.created_at,
        )
        attrs = cls.base_from_disk_attrs(parent, folder_meta) | {"_entity_metadata": meta}
        return cast("Knowledge", _reconstruct(cls, attrs))

    @classmethod
    def write(
        cls,
        host: Folder,
        *,
        name: str,
        sources: list[SourceRef],
        created_by: str,
        body: str,
        cite: Sequence[tuple[Folder, EdgeRole]] = (),
        title: str = "",
    ) -> Knowledge:
        """Write sourced knowledge under *host* (idempotent on *name*)."""
        from .knowledge_write import write_knowledge

        return write_knowledge(
            host,
            name=name,
            cls=cls,
            sources=sources,
            created_by=created_by,
            body=body,
            cite=cite,
            title=title,
        )

    @property
    def metadata(self) -> KnowledgeMetadata:  # type: ignore[override]
        return self._entity_metadata

    def body(self) -> str:
        return self.read_index()

    def set_body(self, text: str) -> None:
        self.write_index(text)

    def cite(
        self,
        ref: Folder,
        *,
        text: str | None = None,
        role: EdgeRole = DEFAULT_EDGE_ROLE,
    ) -> None:
        append_link(self, ref, text=text, role=role)

    def materialize(self) -> None:
        self._disk().mkdir(self.resolve(), parents=True, exist_ok=True)
        self.save()

    def write_meta(self) -> str:
        """Stamp identity on the class-named entity JSON — never ``meta.json``."""
        self.save()
        return self._disk().join(self.resolve(), entity_filename(type(self)))

    def save(self) -> None:
        self._entity_metadata = self._entity_metadata.model_copy(
            update={"id": self._name, "name": self._metadata.name}
        )
        _save_metadata(
            self._entity_metadata,
            self._disk().join(self.resolve(), entity_filename(type(self))),
            fs=self._disk(),
        )


def _knowledge_leaf_classes() -> dict[str, type[Knowledge]]:
    found: dict[str, type[Knowledge]] = {}

    def walk(cls: type[Knowledge]) -> None:
        for sub in cls.__subclasses__():
            found[sub.__name__] = sub
            walk(sub)

    walk(Knowledge)
    return found


def parse_knowledge_class(name: str) -> type[Knowledge]:
    """Map a class name (``Finding``, ``Plan``, …) onto the Knowledge subclass."""
    table = _knowledge_leaf_classes()
    if name in table:
        return table[name]
    raise ValueError(
        f"unknown knowledge class {name!r}; expected one of: {', '.join(sorted(table))}"
    )


class Observation(Knowledge):
    """An observation recorded against a host."""


class Decision(Knowledge):
    """A decision (e.g. a plan-mode experiment record)."""


class Assumption(Knowledge):
    """An assumption the work is relying on."""


class Constraint(Knowledge):
    """A hard constraint."""


class Finding(Knowledge):
    """A result / finding harvested from a run."""


class FailureAnalysis(Knowledge):
    """Analysis of a failed run or plan."""


class ProtocolNote(Knowledge):
    """A protocol snippet."""


class ParameterRationale(Knowledge):
    """Why a parameter was chosen."""


class OpenQuestion(Knowledge):
    """An unanswered question."""


class Plan(Knowledge):
    """The 12-section experiment or project plan book."""


for _cls in (
    Observation,
    Decision,
    Assumption,
    Constraint,
    Finding,
    FailureAnalysis,
    ProtocolNote,
    ParameterRationale,
    OpenQuestion,
    Plan,
):
    register_entity_class(_cls)


def normalize_sources(
    sources: list[SourceRef | Folder | str] | None,
    *,
    default_host: Folder,
) -> list[SourceRef]:
    """Accept SourceRef, Folder, or free strings (dataset: / DOI: / path)."""
    if not sources:
        host_name = type(default_host).__name__
        kind: SourceKind = "experiment" if host_name == "Experiment" else "file"
        return [SourceRef(kind=kind, ref=getattr(default_host, "id", default_host.name))]
    out: list[SourceRef] = []
    for item in sources:
        if isinstance(item, SourceRef):
            out.append(item)
        elif isinstance(item, Folder):
            cls_name = type(item).__name__
            mapped: SourceKind = "file"
            if cls_name == "Run":
                mapped = "run"
            elif cls_name == "Experiment":
                mapped = "experiment"
            out.append(SourceRef(kind=mapped, ref=getattr(item, "id", item.name)))
        else:
            text = str(item)
            if text.startswith(("dataset:", "model:", "plugin:")):
                out.append(SourceRef(kind="file", ref=text))
            elif text.upper().startswith("DOI:") or text.startswith("10."):
                out.append(SourceRef(kind="reference", ref=text))
            else:
                out.append(SourceRef(kind="file", ref=text))
    return out


class HasKnowledge:
    """Typed ``knowledges/`` CRUD. Mixed into Project and Experiment."""

    def add_knowledge(
        self,
        name: str,
        *,
        cls: type[Knowledge],
        body: str = "",
        sources: list[SourceRef | Folder | str] | None = None,
        created_by: str = "user",
        title: str = "",
    ) -> Knowledge:
        from .knowledge_write import write_knowledge

        host = cast("Folder", self)
        cite: list[tuple[Folder, EdgeRole]] = []
        if type(host).__name__ == "Experiment":
            cite.append((host, "derived_from"))
        return write_knowledge(
            host,
            name=name,
            cls=cls,
            sources=normalize_sources(sources, default_host=host),
            created_by=created_by,
            body=body,
            title=title or name,
            cite=cite,
        )

    def knowledge(self, name: str) -> Knowledge:
        """Get existing knowledge by name (must exist)."""
        return cast("Folder", self).get_folder(name, cls=Knowledge)

    def set_knowledge(
        self,
        name: str,
        *,
        cls: type[Knowledge] | None = None,
        body: str | None = None,
        sources: list[SourceRef | Folder | str] | None = None,
        created_by: str | None = None,
        title: str = "",
    ) -> Knowledge:
        from .knowledge_write import write_knowledge

        host = cast("Folder", self)
        item = self.knowledge(name)
        return write_knowledge(
            host,
            name=name,
            cls=cls if cls is not None else type(item),
            sources=(
                normalize_sources(sources, default_host=host)
                if sources is not None
                else list(item.metadata.sources)
            ),
            created_by=created_by if created_by is not None else item.metadata.created_by,
            body=body if body is not None else item.body(),
            title=title or name,
        )

    def del_knowledge(self, name: str) -> None:
        cast("Folder", self).remove_folder(name, cls=Knowledge)

    def has_knowledge(self, name: str) -> bool:
        return cast("Folder", self).has_folder(name, cls=Knowledge)

    def knowledges(self) -> list[Knowledge]:
        return cast("Folder", self).list_folders(cls=Knowledge)


__all__ = [
    "KNOWLEDGE_CONTAINER",
    "KNOWLEDGE_INDEX_FILENAME",
    "PLAN_BOOK_NAME",
    "Assumption",
    "Constraint",
    "Decision",
    "FailureAnalysis",
    "Finding",
    "HasKnowledge",
    "Knowledge",
    "KnowledgeMetadata",
    "Observation",
    "OpenQuestion",
    "ParameterRationale",
    "Plan",
    "ProtocolNote",
    "SourceKind",
    "SourceRef",
    "parse_knowledge_class",
]
