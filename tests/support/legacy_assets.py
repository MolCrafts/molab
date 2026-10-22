"""Hand-written legacy asset records. JSON literals only — no asset package."""

from __future__ import annotations

import json
from pathlib import Path

HELLO = b"hello\n"
DIGEST = "sha256:5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"
LEGACY_ID = "3f2b8c1e-9d4a-4e6b-8f0a-1c2d3e4f5a6b"
CREATED = "2026-01-02T03:04:05"


def write_legacy_data_asset(
    scope_dir: Path,
    *,
    asset_id: str,
    name: str,
    scope_kind: str,
    scope_ids: tuple[str, ...] = (),
    action: str,
    payload: bytes | None,
    source_path: str,
    external_uri: str | None = None,
    rel_path: str | None = None,
    inputs: tuple[str, ...] = (),
    content_hash: str | None = None,
    created_at: str = CREATED,
) -> Path:
    """Write one pre-unified ``asset_id`` record and, when given, its payload."""
    relative = rel_path if rel_path is not None else f"assets/{asset_id}/payload"
    record = {
        "kind": "data",
        "asset_id": asset_id,
        "name": name,
        "scope": {"kind": scope_kind, "ids": list(scope_ids)},
        "path": relative,
        "created_at": created_at,
        "updated_at": created_at,
        "producer": {"inputs": list(inputs)},
        "tags": {},
        "content_hash": content_hash,
        "external_uri": external_uri,
        "source_path": source_path,
        "import_action": action,
    }
    directory = Path(scope_dir) / "assets" / asset_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "asset.json").write_text(json.dumps(record), encoding="utf-8")
    if payload is not None and not external_uri:
        target = Path(scope_dir) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return directory


def write_legacy_domain_asset(
    project_dir: Path,
    *,
    asset_id: str,
    project_id: str,
    title: str,
    artifact_id: str,
    content: dict[str, object],
    slug: str = "model",
    created_at: str = CREATED,
) -> Path:
    """Write one schema-3 promote record (``project_id``, no ``origin``)."""
    directory = Path(project_dir) / "assets" / slug
    versions = directory / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    created_by = {"id": "molab", "type": "system", "name": "Molab"}
    (directory / "asset.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "id": asset_id,
                "project_id": project_id,
                "title": title,
                "created_at": created_at,
                "created_by": created_by,
                "tags": {},
            }
        ),
        encoding="utf-8",
    )
    (versions / "v001.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "id": f"{asset_id}-v001",
                "asset_id": asset_id,
                "source_artifact_id": artifact_id,
                "path": f"projects/p/assets/{slug}/payload",
                "content": content,
                "version": 1,
                "created_at": created_at,
                "created_by": created_by,
            }
        ),
        encoding="utf-8",
    )
    return directory
