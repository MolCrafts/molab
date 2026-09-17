"""``molab.server_plugins`` — third-party HTTP surface mounted by ``create_app``.

A server plugin contributes routers to the gated ``/api`` router and, when it
owns background work, hooks into the application lifespan. molab discovers
them by entry point and never imports a provider package by name, so a package
that sits *above* molab (the harness) can serve its own API from the same
process, on the same origin, under the same session — without molab ever
depending on it.

Declare one in ``pyproject.toml``::

    [project.entry-points."molab.server_plugins"]
    my-plugin = "my_package.server:SERVER_PLUGIN"

Security note: a discovered plugin runs inside the molab server process with
full privileges. Treat it as you would any pip-installed dependency.
"""

from __future__ import annotations

import functools
import importlib.metadata as importlib_metadata
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from mollog import get_logger

if TYPE_CHECKING:
    from fastapi import APIRouter

SERVER_PLUGIN_API_VERSION = "1"
"""Current server plugin API version. Plugins whose ``api_version`` does not
match this value are skipped at discovery time."""

ENTRY_POINT_GROUP = "molab.server_plugins"

logger = get_logger(__name__)


class ServerPlugin:
    """Public descriptor for a third-party molab HTTP surface.

    Plain Python class with an explicit ``__init__`` (not a dataclass, not a
    pydantic ``BaseModel``) because it carries live callables. Logically
    immutable: ``__slots__`` plus a raising ``__setattr__``.

    Attributes:
        id: Globally unique short identifier (kebab-case recommended).
        name: Human-readable display name.
        version: Plugin's own semver string.
        register: Required callable receiving the gated ``/api`` router and
            attaching its own routers to it. Called once per ``create_app``.
        startup: Optional lifespan startup hook. Sync or async.
        shutdown: Optional lifespan shutdown hook — cancel and await the
            plugin's in-flight background work here. Sync or async.
        signal_shutdown: Optional **sync** hook run from the server's signal
            handler, *before* the ASGI server starts draining connections.
            Wake long-poll / SSE generators here; anything slower belongs in
            ``shutdown``.
        api_version: The contract version targeted. Only
            :data:`SERVER_PLUGIN_API_VERSION` is accepted.
    """

    __slots__ = (
        "api_version",
        "id",
        "name",
        "register",
        "shutdown",
        "signal_shutdown",
        "startup",
        "version",
    )

    id: str
    name: str
    version: str
    register: Callable[[APIRouter], None]
    startup: Callable[[], Awaitable[None] | None] | None
    shutdown: Callable[[], Awaitable[None] | None] | None
    signal_shutdown: Callable[[], None] | None
    api_version: str

    def __init__(
        self,
        *,
        id: str,
        name: str,
        version: str,
        register: Callable[[APIRouter], None],
        startup: Callable[[], Awaitable[None] | None] | None = None,
        shutdown: Callable[[], Awaitable[None] | None] | None = None,
        signal_shutdown: Callable[[], None] | None = None,
        api_version: str = SERVER_PLUGIN_API_VERSION,
    ) -> None:
        for field, value in (
            ("id", id),
            ("name", name),
            ("version", version),
            ("register", register),
            ("startup", startup),
            ("shutdown", shutdown),
            ("signal_shutdown", signal_shutdown),
            ("api_version", api_version),
        ):
            object.__setattr__(self, field, value)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable; cannot assign to {name!r}")


@functools.cache
def _discover_server_uncached() -> tuple[ServerPlugin, ...]:
    """Walk the ``molab.server_plugins`` entry-point group exactly once.

    Cached at module level. Tests reset via ``cache_clear()``.
    """
    seen: set[str] = set()
    discovered: list[ServerPlugin] = []

    for ep in importlib_metadata.entry_points().select(group=ENTRY_POINT_GROUP):
        plugin = _safe_load(ep)
        if plugin is None:
            continue
        if plugin.id in seen:
            ep_name = getattr(ep, "name", "<unknown>")
            logger.warning(
                f"duplicate plugin id '{plugin.id}' from entry point '{ep_name}' — keeping first"
            )
            continue
        seen.add(plugin.id)
        discovered.append(plugin)

    return tuple(discovered)


def _safe_load(ep) -> ServerPlugin | None:  # noqa: ANN001
    """Load a single entry point, returning ``None`` on any error."""
    name = getattr(ep, "name", "<unknown>")
    try:
        obj = ep.load()
    except Exception as exc:
        logger.warning(f"failed to load server plugin entry point '{name}': {exc}")
        return None

    if not isinstance(obj, ServerPlugin):
        logger.warning(
            f"entry point '{name}' did not return a ServerPlugin instance "
            f"(got {type(obj).__name__}); skipping"
        )
        return None

    if obj.api_version != SERVER_PLUGIN_API_VERSION:
        logger.warning(
            f"plugin '{obj.id}' targets api_version='{obj.api_version}' but "
            f"molab expects '{SERVER_PLUGIN_API_VERSION}'; skipping"
        )
        return None

    return obj


def discover_server_plugins() -> tuple[ServerPlugin, ...]:
    """Return all discoverable third-party :class:`ServerPlugin` instances.

    Cached after the first call. Entry-point load failures are swallowed and
    logged — the caller always receives a tuple, possibly empty.
    """
    return _discover_server_uncached()


def signal_shutdown_server_plugins() -> None:
    """Run every plugin's sync ``signal_shutdown`` hook, ignoring failures.

    Called from the server's signal handler, before connection drain. A
    plugin that raises here must not prevent the others from being woken, nor
    block the shutdown path.
    """
    for plugin in discover_server_plugins():
        hook = plugin.signal_shutdown
        if hook is None:
            continue
        try:
            hook()
        except Exception as exc:  # never block signal handling on a soft failure
            logger.warning(f"plugin '{plugin.id}' signal_shutdown raised; ignoring: {exc}")


__all__ = [
    "ENTRY_POINT_GROUP",
    "SERVER_PLUGIN_API_VERSION",
    "ServerPlugin",
    "discover_server_plugins",
    "signal_shutdown_server_plugins",
]
