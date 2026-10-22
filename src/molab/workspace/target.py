"""Local addresses and molq-registered destination addresses."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .fs import FileSystem
from .models import ComputeTarget
from .targets import resolve_compute_target, to_filesystem

if TYPE_CHECKING:
    from .workspace import Workspace


class LocalTarget(ComputeTarget):
    def __init__(self, path: Path | str | None = None, **data: Any) -> None:  # noqa: ANN401
        data.setdefault("scratch_root", str(path if path is not None else Path.cwd()))
        data.setdefault("name", data["scratch_root"])
        super().__init__(**data)

    @property
    def path(self) -> Path:
        return Path(self.scratch_root)

    def __str__(self) -> str:
        return str(self.path)


class RemoteTarget(ComputeTarget):
    def __init__(self, *, path: str | None = None, **data: Any) -> None:  # noqa: ANN401
        if path is not None:
            data.setdefault("scratch_root", path)
        data.setdefault("name", data.get("cluster_id", ""))
        super().__init__(**data)

    @property
    def path(self) -> str:
        return self.scratch_root

    def __str__(self) -> str:
        return f"{self.cluster_id}:{self.path}"


Target = LocalTarget | RemoteTarget


class TargetNeedsResolution(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Target {name!r} requires a workspace")
        self.name = name


class TargetNotFound(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"No compute target named {name!r}")


def parse_target(raw: str | None) -> Target:
    """Parse with molq.Path; remote prefixes are registered destinations."""
    from molq import Path as MolqPath

    from .connection import get_client

    if raw and raw.startswith("@"):
        raise TargetNeedsResolution(raw)
    parsed = MolqPath(raw or str(Path.cwd()))
    if parsed.cluster is None:
        return LocalTarget(Path(parsed.as_posix()).expanduser().resolve())
    client = get_client()
    definition = client.cluster(parsed.cluster).definition()
    return RemoteTarget(
        name=definition["name"],
        registry_id=client.rpc("molq.hello")["registry_id"],
        cluster_id=definition["id"],
        path=parsed.as_posix(),
    )


def resolve_target(raw: str | None, ws: Workspace | None = None) -> tuple[Target, FileSystem]:
    if raw and raw.startswith("@"):
        if ws is None:
            raise TargetNeedsResolution(raw)
        try:
            record = resolve_compute_target(ws, raw[1:])
        except KeyError:
            raise TargetNotFound(raw[1:]) from None
        target: Target = (
            RemoteTarget(**record.model_dump())
            if record.cluster_id
            else LocalTarget(**record.model_dump())
        )
    else:
        target = parse_target(raw)
    return target, to_filesystem(target)


__all__ = [
    "LocalTarget",
    "RemoteTarget",
    "Target",
    "TargetNeedsResolution",
    "TargetNotFound",
    "parse_target",
    "resolve_target",
]
