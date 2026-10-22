"""Manifest-scanner imports stay inside the asset package (arch-own-05d)."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
MOLAB = SRC / "molab"
ASSETS = MOLAB / "workspace" / "assets"
INIT = MOLAB / "workspace" / "__init__.py"

_FORBIDDEN_NAMES = frozenset(
    {"AssetsView", "scan_assets", "get_asset", "find_by_content_hash", "scan", "view"}
)

# Files and symbols this spec removes. The assertions below use these tuples.
DELETED_FILES = ("server/routes/_scope.py",)
DELETED_SYMBOLS = ("asset_has_sidecar",)


def _allowed(path: Path) -> bool:
    resolved = path.resolve()
    if resolved == INIT.resolve():
        return True
    try:
        resolved.relative_to(ASSETS.resolve())
    except ValueError:
        return False
    return True


def _forbidden_module(module: str | None) -> bool:
    if module is None:
        return False
    parts = module.split(".")
    return "assets" in parts and ({"scan", "view"} & set(parts))


def _hits() -> list[str]:
    found: list[str] = []
    for path in MOLAB.rglob("*.py"):
        if "__pycache__" in path.parts or _allowed(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _forbidden_module(alias.name):
                        found.append(f"{path}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                names = [alias.name for alias in node.names]
                if _forbidden_module(node.module) or any(
                    name in _FORBIDDEN_NAMES for name in names
                ):
                    found.append(
                        f"{path}:{node.lineno}: from {node.module} import {', '.join(names)}"
                    )
    return found


def test_manifest_scanner_is_not_imported_outside_assets() -> None:
    assert _hits() == []


def test_scope_helper_and_sidecar_predicate_are_gone() -> None:
    for relative in DELETED_FILES:
        assert not (MOLAB / relative).exists(), relative
    offenders = [
        path
        for path in SRC.rglob("*.py")
        if "__pycache__" not in path.parts
        and any(symbol in path.read_text(encoding="utf-8") for symbol in DELETED_SYMBOLS)
    ]
    assert offenders == []


_DELETED_ASSET_MODULES = (
    "manifest",
    "scan",
    "view",
    "accessors",
    "data",
    "artifact",
    "log",
    "checkpoint",
    "error",
    "_adapter",
    "base",
)
_DELETED_ASSET_SYMBOLS = (
    "ArtifactAsset",
    "AssetManifest",
    "AssetsView",
    "CheckpointAsset",
    "DataAsset",
    "DataAssetLibrary",
    "ErrorTraceAsset",
    "LogAsset",
    "Producer",
)


def test_manifest_family_is_gone() -> None:
    import molab.ids as ids
    import molab.workflow.protocols as protocols
    import molab.workspace as workspace
    import molab.workspace.assets as assets
    import molab.workspace.utils as utils

    assert assets.__all__ == ["lineage"]
    assert workspace.Asset is workspace.domain.Asset
    assert "UnmigratedAssetError" in workspace.__all__
    for name in _DELETED_ASSET_SYMBOLS:
        assert not hasattr(workspace, name), name
    for module in _DELETED_ASSET_MODULES:
        assert not (ASSETS / f"{module}.py").exists(), module
    assert not hasattr(protocols, "AssetsViewLike")
    assert "assets" not in protocols.UpstreamViewLike.__annotations__
    assert not hasattr(ids, "generate_asset_id")
    assert "generate_asset_id" not in getattr(ids, "__all__", ())
    assert not hasattr(utils, "generate_asset_id")

    quoted = '"assets.json"'
    hits = sorted(
        path.relative_to(MOLAB).as_posix()
        for path in MOLAB.rglob("*.py")
        if "__pycache__" not in path.parts and quoted in path.read_text(encoding="utf-8")
    )
    assert hits == ["cli/migrate_cmd.py", "workspace/artifact_repository.py"]
