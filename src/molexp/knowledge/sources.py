"""Named knowledge sources — a registry of OKF bundles (group wikis).

A research group's knowledge does not live in one place. There is the lab wiki
(often its own git repo), maybe a second one for a sub-project, and the
workspace you happen to be standing in. Retrieval should reach all of them and
say which one each answer came from.

So a *source* is a name bound to a directory. The store is two-tier, mirroring
:mod:`molexp.agent.mcp.store`: **User** (``~/.molexp/knowledge.json``) and
**Workspace** (``<root>/.molexp/knowledge.json``). When a name appears in both,
the Workspace entry **fully replaces** the User one — no per-field merge. Keep
that rule in step with the MCP store if it ever changes; two settings models
that look identical but behave differently are worse than either.

Deliberately import-cheap — stdlib + pydantic (+ the light ``bundle_index``
models). ``Bundle`` is imported inside :func:`open_bundle` and
:func:`search_sources`, so a caller that merely *lists* registered wikis (an MCP
tool building its catalog, a CLI printing a table) never loads yaml, pathspec or
the OKF substrate.
"""

from __future__ import annotations

import json
import os
import re
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator

# ``bundle_index`` is re + pydantic only, so importing it eagerly costs nothing;
# ``SourcedHit`` needs ``SearchHit`` at runtime for pydantic to build its schema.
# ``bundle`` — which pulls yaml + pathspec — stays lazy.
from .bundle_index import SearchHit

if TYPE_CHECKING:
    from collections.abc import Callable

    from molexp.fs import PathArg

    from .bundle import Bundle
    from .bundle_index import SearchResult

__all__ = [
    "KNOWLEDGE_CONFIG_FILENAME",
    "MOLEXP_DIR",
    "KnowledgeScope",
    "KnowledgeSourceStore",
    "SourceNotFoundError",
    "SourcedHit",
    "WikiSource",
    "open_bundle",
    "resolve_source",
    "search_sources",
]

KNOWLEDGE_CONFIG_FILENAME = "knowledge.json"
"""Config basename, used at both scopes."""

MOLEXP_DIR = ".molexp"
"""Workspace-local hidden dir — the established home for molexp's own state
(``<root>/.molexp/git``, ``<root>/.molexp/background``). Note this differs from
MCP's ``<root>/.mcp.json``, which sits at the root only for Claude-Code
compatibility; there is no such constraint here."""

USER_DIR = Path.home() / ".molexp"

#: Source names become JSON keys, CLI arguments and ``<source>:<path>`` ref
#: prefixes. Same path-safe alphabet as MCP server names.
SOURCE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class SourceNotFoundError(LookupError):
    """Raised when a named knowledge source is not registered."""

    def __init__(self, name: str) -> None:
        super().__init__(f"knowledge source {name!r} is not registered")
        self.name = name


class KnowledgeScope(StrEnum):
    """Which settings layer an entry belongs to."""

    USER = "user"
    WORKSPACE = "workspace"


class WikiSource(BaseModel, frozen=True):
    """One registered OKF bundle.

    Attributes:
        name: The handle used to address it (``--source lab-wiki``, and the
            prefix of a ``<source>:<rel_path>`` ref).
        root: The bundle directory. ``~`` is expanded on read, so a config file
            stays portable between machines.
        description: Optional human note — shown in listings and handed to
            agents so they can tell two wikis apart.
    """

    name: str
    root: str
    description: str = ""

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not SOURCE_NAME_PATTERN.match(value):
            raise ValueError(
                f"invalid knowledge source name {value!r}: expected lowercase "
                "letters, digits, '-' or '_' (max 64 chars, not starting with -/_)"
            )
        return value

    def path(self) -> Path:
        """The bundle directory, with ``~`` expanded."""
        return Path(self.root).expanduser()


class KnowledgeSourceStore:
    """Two-tier (User + Workspace) registry of named OKF bundles."""

    def __init__(
        self,
        workspace_root: PathArg | None = None,
        *,
        user_dir: PathArg | None = None,
    ) -> None:
        """Bind the store to its two config files; read nothing yet.

        Args:
            workspace_root: The workspace whose ``.molexp/knowledge.json``
                forms the upper tier; ``None`` uses the user tier alone.
            user_dir: Override for ``~/.molexp`` (tests).
        """
        self._workspace_root = Path(os.fspath(workspace_root)) if workspace_root else None
        self._user_dir = Path(os.fspath(user_dir)) if user_dir else USER_DIR

    def config_path(self, scope: KnowledgeScope) -> Path:
        """The config file backing *scope*.

        Raises:
            ValueError: For the workspace scope with no workspace root bound.
        """
        if scope is KnowledgeScope.USER:
            return self._user_dir / KNOWLEDGE_CONFIG_FILENAME
        if self._workspace_root is None:
            raise ValueError("workspace scope requires a workspace_root")
        return self._workspace_root / MOLEXP_DIR / KNOWLEDGE_CONFIG_FILENAME

    def _read(self, scope: KnowledgeScope) -> dict[str, WikiSource]:
        """Parse one tier; a missing or malformed file yields no sources.

        A corrupt config must not make every knowledge command fail — the other
        tier, and the rest of the CLI, keep working.
        """
        try:
            path = self.config_path(scope)
        except ValueError:
            return {}
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        entries = raw.get("sources") if isinstance(raw, dict) else None
        if not isinstance(entries, dict):
            return {}
        out: dict[str, WikiSource] = {}
        for name, value in entries.items():
            if isinstance(value, str):  # shorthand: {"lab-wiki": "/data/wiki"}
                value = {"root": value}
            if not isinstance(value, dict):
                continue
            try:
                out[name] = WikiSource(name=name, **{k: v for k, v in value.items() if k != "name"})
            except (TypeError, ValueError):
                continue  # one bad entry never hides the rest
        return out

    def _write(self, scope: KnowledgeScope, sources: dict[str, WikiSource]) -> None:
        path = self.config_path(scope)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sources": {
                name: source.model_dump(exclude={"name"}, exclude_defaults=True)
                for name, source in sorted(sources.items())
            }
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)  # atomic: a torn config would break every knowledge command

    def list(self) -> list[tuple[WikiSource, KnowledgeScope]]:
        """Every effective source with the scope it came from, name-ascending.

        A workspace entry fully replaces a user entry of the same name.
        """
        merged: dict[str, tuple[WikiSource, KnowledgeScope]] = {
            name: (source, KnowledgeScope.USER)
            for name, source in self._read(KnowledgeScope.USER).items()
        }
        for name, source in self._read(KnowledgeScope.WORKSPACE).items():
            merged[name] = (source, KnowledgeScope.WORKSPACE)
        return [merged[name] for name in sorted(merged)]

    def get(self, name: str) -> WikiSource:
        """The effective source named *name*.

        Raises:
            SourceNotFoundError: If no tier registers that name.
        """
        for source, _scope in self.list():
            if source.name == name:
                return source
        raise SourceNotFoundError(name)

    def add(self, source: WikiSource, *, scope: KnowledgeScope = KnowledgeScope.USER) -> None:
        """Register (or replace) *source* at *scope*."""
        sources = self._read(scope)
        sources[source.name] = source
        self._write(scope, sources)

    def remove(self, name: str, *, scope: KnowledgeScope = KnowledgeScope.USER) -> None:
        """Unregister *name* at *scope*.

        Raises:
            SourceNotFoundError: If that scope does not register the name. It is
                raised rather than ignored so removing a *shadowed* user entry
                by asking the workspace scope tells you what actually happened.
        """
        sources = self._read(scope)
        if name not in sources:
            raise SourceNotFoundError(name)
        del sources[name]
        self._write(scope, sources)


def resolve_source(
    name: str,
    *,
    workspace_root: PathArg | None = None,
    store: KnowledgeSourceStore | None = None,
) -> Path:
    """The directory registered as *name*.

    Args:
        name: The registered source name.
        workspace_root: Workspace supplying the upper config tier.
        store: An explicit store, overriding *workspace_root* — lets a caller
            point at a different config root (tests, a sandboxed host).

    Raises:
        SourceNotFoundError: If the name is not registered.
    """
    return (store or KnowledgeSourceStore(workspace_root)).get(name).path()


def open_bundle(
    name: str,
    *,
    workspace_root: PathArg | None = None,
    store: KnowledgeSourceStore | None = None,
) -> Bundle:
    """Open the registered source *name* as a :class:`Bundle`.

    Raises:
        SourceNotFoundError: If the name is not registered.
    """
    from .bundle import Bundle

    return Bundle(resolve_source(name, workspace_root=workspace_root, store=store))


class SourcedHit(BaseModel, frozen=True):
    """One search hit, tagged with the source it came from.

    Attributes:
        source: The registered source name (``""`` for the active workspace).
        hit: The underlying :class:`~molexp.knowledge.bundle_index.SearchHit`.
        abs_path: Absolute path of the Concept's ``index.md`` — the file itself,
            so a caller can hand over or open the whole document.
        rank: 1-based position in the fused ordering.
    """

    source: str
    hit: SearchHit
    abs_path: str
    rank: int

    @property
    def ref(self) -> str:
        """The portable ``<source>:<bundle-relative-path>`` reference."""
        return f"{self.source}:{self.hit.entry.path}" if self.source else self.hit.entry.path


#: Reciprocal-rank-fusion constant. The same value molmcp uses for the same job.
RRF_K = 60


def search_sources(
    query: str,
    *,
    sources: list[str] | None = None,
    workspace_root: PathArg | None = None,
    include_workspace: bool = True,
    limit: int = 10,
    concept_type: str | None = None,
    tag: str | None = None,
    store: KnowledgeSourceStore | None = None,
    workspace_searcher: Callable[[], SearchResult] | None = None,
) -> list[SourcedHit]:
    """Search several registered bundles at once and fuse the results.

    Each source is searched independently, then the per-source rankings are
    merged by **reciprocal rank fusion** (``1 / (RRF_K + rank)``) rather than by
    raw score. BM25 scores are only comparable within one corpus — IDF is
    computed against that corpus — so sorting raw scores across bundles would
    quietly favour whichever wiki happens to be smaller. Fusing ranks compares
    only each source's own opinion of its documents, which is the part that
    transfers.

    Args:
        query: The search text.
        sources: Source names to search; ``None`` searches all registered ones.
        workspace_root: The active workspace — supplies the workspace config
            tier and, with *include_workspace*, is itself searched.
        include_workspace: Also search *workspace_root* as an unnamed bundle.
        limit: Maximum fused hits to return.
        concept_type: Exact Concept ``type`` filter, applied per source.
        tag: Tag filter, applied per source.
        store: An explicit source store, overriding *workspace_root*'s.
        workspace_searcher: How to search the workspace itself, when given —
            a host that already holds a scanned index (a server read model)
            or opens the workspace with its own pruning passes a closure over
            the same *query* / filters / *limit*; ``None`` opens a plain
            :class:`~molexp.knowledge.bundle.Bundle` over *workspace_root*.
            Registered sources are always searched per query.

    Returns:
        The fused hits, best first, each tagged with its source and the absolute
        path of its ``index.md``.
    """
    from .bundle import Bundle

    store = store or KnowledgeSourceStore(workspace_root)
    targets: list[tuple[str, Path]] = []
    if include_workspace and workspace_root is not None:
        targets.append(("", Path(os.fspath(workspace_root))))
    wanted = set(sources) if sources is not None else None
    for source, _scope in store.list():
        if wanted is not None and source.name not in wanted:
            continue
        targets.append((source.name, source.path()))

    fused: dict[tuple[str, str], tuple[float, str, SearchHit, Path]] = {}
    for name, root in targets:
        if not root.is_dir():
            continue  # a registered wiki that is not mounted today is not an error
        if name == "" and workspace_searcher is not None:
            result = workspace_searcher()
        else:
            result = Bundle(root).search(query, concept_type=concept_type, tag=tag, limit=limit)
        for rank, hit in enumerate(result.hits, start=1):
            key = (name, hit.entry.path)
            fused[key] = (1.0 / (RRF_K + rank), name, hit, root)

    ordered = sorted(fused.items(), key=lambda kv: (-kv[1][0], kv[0][0], kv[0][1]))
    return [
        SourcedHit(
            source=name,
            hit=hit,
            abs_path=str(root / hit.entry.path / "index.md"),
            rank=position,
        )
        for position, (_key, (_rrf, name, hit, root)) in enumerate(ordered[:limit], start=1)
    ]
