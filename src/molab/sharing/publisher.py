"""Owner-side projection and publication; gateway never opens these files."""

from __future__ import annotations

import contextlib
import http.client
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from mollog import get_logger

from molab.atomicio import atomic_write_json
from molab.ids import compute_definition_hash
from molab.plugins.metrics.wal import discover_mlp_jsonl, read_run_metrics
from molab.workspace import Workspace
from molab.workspace.models import RunStatus
from molab.workspace.refs import parse_ref

from .models import (
    ApprovedPublication,
    BeginPublication,
    PublicationBatch,
    PublicationPreview,
    PublicationSelection,
    PublishedExperiment,
    PublishedProject,
    PublishedRun,
    ScalarPoint,
)
from .settings import WorkerSettings
from .store import SharingError

logger = get_logger(__name__)


def build_preview(workspace: Workspace, selection: PublicationSelection) -> PublicationPreview:
    """Read only approved identities/fields using built-in metadata/JSONL readers."""
    project = workspace.get_project(selection.project_id)
    experiments = {e.id: e for e in project.list_experiments()}
    if not set(selection.experiment_ids).issubset(experiments):
        raise SharingError(422, "Selected experiment does not belong to the project")
    published_experiments = [
        PublishedExperiment(
            id=e.id,
            name=e.name,
            description=e.metadata.description if selection.include_descriptions else "",
        )
        for e in experiments.values()
        if e.id in selection.experiment_ids
    ]
    runs: list[PublishedRun] = []
    for reference in dict.fromkeys(selection.run_refs):
        ref = parse_ref(reference, kind="run")
        if ref.experiment_id not in selection.experiment_ids:
            raise SharingError(422, "Every selected run requires its selected experiment")
        assert ref.experiment_id is not None and ref.run_id is not None
        run = experiments[ref.experiment_id].get_run(ref.run_id)
        metrics: dict[str, list[ScalarPoint]] = {}
        attempts = run.executions if selection.metric_keys else []
        if attempts:
            wal = discover_mlp_jsonl(run.execution_dir(attempts[-1].id), fs=workspace.fs)
            if wal and workspace.fs.getsize(wal) > 8 * 1024 * 1024:
                raise SharingError(
                    422, "Selected metrics source exceeds the 8 MiB publication limit"
                )
            for key in selection.metric_keys:
                values = read_run_metrics(
                    run.execution_dir(attempts[-1].id),
                    fs=workspace.fs,
                    metric_type="scalar",
                    key=key,
                    limit=2001,
                )
                if len(values.records) > 2000:
                    raise SharingError(
                        422, "A selected metric exceeds the 2000-point publication limit"
                    )
                metrics[key] = [
                    ScalarPoint.model_validate({"value": r["v"], "step": r.get("s")})
                    for r in values.records
                ]
        runs.append(
            PublishedRun.model_validate(
                {
                    "id": run.id,
                    "experiment_id": ref.experiment_id,
                    "name": run.id,
                    "status": RunStatus(run.status_label),
                    "parameters": {
                        key: run.parameters[key]
                        for key in selection.parameter_keys
                        if key in run.parameters
                    },
                    "metrics": metrics,
                }
            )
        )
    return PublicationPreview(
        workspace_id=workspace.metadata.id,
        project=PublishedProject(
            id=project.id,
            name=project.name,
            description=project.description if selection.include_descriptions else "",
        ),
        experiments=published_experiments,
        runs=runs,
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        # Source credentials must never follow a redirect to another endpoint.
        del req, fp, code, msg, headers, newurl
        return


class Publisher:
    def __init__(self, workspace: Workspace, settings: WorkerSettings) -> None:
        self.workspace = workspace
        self.settings = settings
        self.approvals = Path(str(workspace.root)) / ".molab" / "sharing"
        self._lock = threading.RLock()
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def request(self, method: str, path: str, body: object = None) -> dict[str, object]:
        encoded = json.dumps(body, allow_nan=False).encode() if body is not None else None
        if encoded is not None and len(encoded) > 2 * 1024 * 1024:
            raise SharingError(413, "A publication batch exceeds 2 MiB")
        request = urllib.request.Request(
            str(self.settings.gateway_url).rstrip("/") + path,
            data=encoded,
            method=method,
            headers={
                "Authorization": "Bearer " + self.settings.source_token.get_secret_value(),
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener.open(request, timeout=10) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise SharingError(502, "Gateway response exceeds limit")
                result = json.loads(raw) if raw else {}
                if not isinstance(result, dict):
                    raise SharingError(502, "Gateway returned an invalid response")
                return result
        except urllib.error.HTTPError as exc:
            detail = "Gateway rejected publication"
            with (
                contextlib.closing(exc),
                contextlib.suppress(ValueError, OSError, http.client.HTTPException),
            ):
                payload = json.loads(exc.read(16384))
                if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
                    detail = payload["detail"][:500]
            raise SharingError(
                exc.code if exc.code in {403, 404, 409, 413, 422, 429} else 502, detail
            ) from exc
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise SharingError(502, "Sharing gateway is unavailable") from exc

    def verify_source(self) -> str:
        identity = self.request("GET", "/internal/sharing/source")
        expected = {
            "principal_id": self.settings.principal_id,
            "cluster_id": self.settings.cluster_id,
            "uid": self.settings.uid,
        }
        if any(identity.get(key) != value for key, value in expected.items()):
            raise SharingError(403, "Source identity does not match the workspace service")
        return str(identity["id"])

    def _upload(self, preview: PublicationPreview, *, activate: bool = False) -> dict[str, object]:
        query = urllib.parse.urlencode(
            {"workspace_id": preview.workspace_id, "project_id": preview.project.id}
        )
        current = self.request("GET", "/internal/sharing/source/project?" + query)
        begin = BeginPublication.model_validate(
            {
                "workspace_id": preview.workspace_id,
                "project": preview.project,
                "base_version": current.get("current_version"),
                "activate": activate,
            }
        )
        draft = self.request(
            "POST", "/internal/sharing/publications", begin.model_dump(mode="json")
        )
        base = f"/internal/sharing/publications/{draft['version_id']}"
        batch_id = 0
        batch = PublicationBatch()
        try:
            for kind, objects in (("experiments", preview.experiments), ("runs", preview.runs)):
                for obj in objects:
                    value = batch.model_dump(mode="json")
                    value[kind].append(obj.model_dump(mode="json"))
                    if len(json.dumps(value).encode()) > 1900000 or len(value[kind]) > 500:
                        self.request(
                            "PUT", f"{base}/batches/{batch_id}", batch.model_dump(mode="json")
                        )
                        batch_id += 1
                        batch = PublicationBatch.model_validate(
                            {kind: [obj.model_dump(mode="json")]}
                        )
                    else:
                        batch = PublicationBatch.model_validate(value)
            self.request("PUT", f"{base}/batches/{batch_id}", batch.model_dump(mode="json"))
            return self.request("POST", base + "/commit")
        except (SharingError, ValueError, OSError):
            with contextlib.suppress(SharingError):
                self.request("DELETE", base)
            raise

    def publish(self, selection: PublicationSelection, preview_digest: str) -> dict[str, object]:
        with self._lock:
            source_id = self.verify_source()
            preview = build_preview(self.workspace, selection)
            if compute_definition_hash(preview.model_dump(mode="json")) != preview_digest:
                raise SharingError(409, "Preview changed; review it again before publishing")
            result = self._upload(preview, activate=True)
            approval = ApprovedPublication(
                source_id=source_id,
                workspace_id=preview.workspace_id,
                shared_project_id=str(result["project_id"]),
                selection=selection,
                last_digest=preview_digest,
            )
            # The directory is private workspace state, not an authorization store.
            self.approvals.mkdir(parents=True, mode=0o700, exist_ok=True)
            atomic_write_json(
                self.approvals / f"{approval.shared_project_id}.json",
                approval.model_dump(mode="json"),
            )
            return result

    def refresh_all(self) -> None:
        with self._lock:
            if not self.approvals.is_dir():
                return
            source_id = self.verify_source()
            for path in sorted(self.approvals.glob("*.json")):
                try:
                    approval = ApprovedPublication.model_validate_json(path.read_text())
                    if (
                        approval.source_id != source_id
                        or approval.workspace_id != self.workspace.metadata.id
                    ):
                        continue
                    query = urllib.parse.urlencode(
                        {
                            "workspace_id": approval.workspace_id,
                            "project_id": approval.selection.project_id,
                        }
                    )
                    current = self.request("GET", "/internal/sharing/source/project?" + query)
                    if current.get("id") != approval.shared_project_id or not current.get("active"):
                        continue
                    preview = build_preview(self.workspace, approval.selection)
                    digest = compute_definition_hash(preview.model_dump(mode="json"))
                    if digest != approval.last_digest:
                        self._upload(preview)
                        atomic_write_json(
                            path,
                            approval.model_copy(update={"last_digest": digest}).model_dump(
                                mode="json"
                            ),
                        )
                except (ValueError, OSError, LookupError, SharingError):
                    logger.warning("Could not refresh an approved project publication")
