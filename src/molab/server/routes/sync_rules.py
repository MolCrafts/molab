"""HTTP surface for per-path remote sync rules.

The body is the form: path, direction, what to copy, and when. This module
does not accept rsync patterns. Local workspaces have no mirror and
respond 409.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field

from molab.server.deps.scope_root import ScopeRoot
from molab.server.schemas._wire import ApiModel
from molab.workspace.fs_cached import CachedRemoteFS
from molab.workspace.sync_rules import (
    SyncBusyError,
    SyncFailedError,
    SyncRule,
    SyncRulesError,
    SyncRun,
    delete_rule,
    execute_rule,
    get_rule,
    load_rules,
    relativize,
    upsert_rule,
)

from ..dependencies import get_workspace

router = APIRouter(tags=["workspace"])


class SyncRuleWrite(ApiModel):
    """Form fields for one path. There is one rule per path."""

    path: str
    kind: str
    direction: str = "pull"
    content: str = "everything"
    types: list[str] = Field(default_factory=list)
    extra_files: str = "keep"
    when: str = "manual"
    interval_minutes: int = 15


class SyncRuleResponse(ApiModel):
    id: str
    path: str
    kind: str
    direction: str
    content: str
    types: list[str]
    extra_files: str
    when: str
    interval_minutes: int
    last_run_at: str | None = None
    last_status: str | None = None
    last_output: str | None = None


class SyncRuleListResponse(ApiModel):
    rules: list[SyncRuleResponse]


class SyncRunResponse(ApiModel):
    rule: SyncRuleResponse
    output: str
    dry_run: bool


def _require_cached_fs(workspace: object) -> CachedRemoteFS:
    fs = getattr(workspace, "fs", None)
    if not isinstance(fs, CachedRemoteFS):
        raise HTTPException(
            status_code=409,
            detail="Active workspace has no cache (local workspaces are not cached).",
        )
    return fs


def _rule_response(rule: SyncRule) -> SyncRuleResponse:
    return SyncRuleResponse(
        id=rule.id,
        path=rule.path,
        kind=rule.kind,
        direction=rule.direction,
        content=rule.content,
        types=list(rule.types),
        extra_files=rule.extra_files,
        when=rule.when,
        interval_minutes=rule.interval_minutes,
        last_run_at=rule.last_run_at,
        last_status=rule.last_status,
        last_output=rule.last_output,
    )


def _run_response(result: SyncRun) -> SyncRunResponse:
    return SyncRunResponse(
        rule=_rule_response(result.rule), output=result.output, dry_run=result.dry_run
    )


@router.get("/sync-rules", response_model=SyncRuleListResponse)
def list_sync_rules(workspace: ScopeRoot = Depends(get_workspace)) -> SyncRuleListResponse:
    """List sync rules for the active remote workspace."""
    fs = _require_cached_fs(workspace)
    try:
        rules = load_rules(fs.mirror_root)
    except SyncRulesError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SyncRuleListResponse(rules=[_rule_response(rule) for rule in rules])


@router.post("/sync-rules", response_model=SyncRuleResponse)
def save_sync_rule(
    body: SyncRuleWrite,
    workspace: ScopeRoot = Depends(get_workspace),
) -> SyncRuleResponse:
    """Create or replace the rule for this path. Last-run fields are kept."""
    fs = _require_cached_fs(workspace)
    try:
        relative = relativize(str(workspace.root), body.path)
        rule = upsert_rule(
            fs.mirror_root,
            path=relative,
            kind=body.kind,
            direction=body.direction,
            content=body.content,
            types=body.types,
            extra_files=body.extra_files,
            when=body.when,
            interval_minutes=body.interval_minutes,
        )
    except SyncRulesError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _rule_response(rule)


@router.delete("/sync-rules/{rule_id}", status_code=204)
def remove_sync_rule(
    rule_id: str,
    workspace: ScopeRoot = Depends(get_workspace),
) -> Response:
    """Delete one rule."""
    fs = _require_cached_fs(workspace)
    try:
        delete_rule(fs.mirror_root, rule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Sync rule not found.") from exc
    except SyncRulesError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/sync-rules/{rule_id}/preview", response_model=SyncRunResponse)
def preview_sync_rule(
    rule_id: str,
    workspace: ScopeRoot = Depends(get_workspace),
) -> SyncRunResponse:
    """Dry-run one rule. Files and last-run fields stay unchanged."""
    return _execute(rule_id, workspace, dry_run=True)


@router.post("/sync-rules/{rule_id}/run", response_model=SyncRunResponse)
def run_sync_rule(
    rule_id: str,
    workspace: ScopeRoot = Depends(get_workspace),
) -> SyncRunResponse:
    """Copy one rule now and record the result on it."""
    return _execute(rule_id, workspace, dry_run=False)


def _execute(rule_id: str, workspace: ScopeRoot, *, dry_run: bool) -> SyncRunResponse:
    fs = _require_cached_fs(workspace)
    try:
        get_rule(fs.mirror_root, rule_id)
        result = execute_rule(fs, str(workspace.root), rule_id, dry_run=dry_run)
    except SyncBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Sync rule not found.") from exc
    except SyncFailedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except SyncRulesError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _run_response(result)
