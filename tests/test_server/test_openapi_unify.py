"""OpenAPI contract checks for the unified wire surface (openapi-unify-01)."""

from __future__ import annotations

from pathlib import Path

from molexp.server.app import create_app


def test_openapi_has_flat_create_run_and_workspace_cache() -> None:
    schema = create_app(serve_static=False).openapi()
    paths = schema.get("paths", {})
    assert "/api/runs" in paths
    assert "post" in paths["/api/runs"]
    assert paths["/api/runs"]["post"].get("operationId") == "createRun"
    assert "/api/executions" not in paths
    assert "/api/workspace/cache/stats" in paths
    assert "/api/cache/stats" not in paths


def test_openapi_execution_create_request_uses_camel_case_fields() -> None:
    schema = create_app(serve_static=False).openapi()
    components = schema.get("components", {}).get("schemas", {})
    req = components.get("ExecutionCreateRequest", {})
    props = req.get("properties", {})
    assert "projectId" in props
    assert "experimentId" in props
    assert "project_id" not in props


def test_dump_openapi_is_deterministic(tmp_path: Path) -> None:
    from scripts.dump_openapi import dump_openapi

    first = dump_openapi(tmp_path / "a.json")
    second = dump_openapi(tmp_path / "b.json")
    assert first.read_text() == second.read_text()
