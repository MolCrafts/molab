"""Read-only source previews shared by CLI and isolated HTTP preview children."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from molab._typing import JSONValue


def _existing_experiment_id(root: Path, rel_path: str) -> str | None:
    """The id of the experiment recorded at ``root/rel_path``, or ``None``."""
    from molab import frontmatter
    from molab.fs import LocalFS
    from molab.workspace.entity_record import INDEX_FILENAME
    from molab.workspace.folder import WORKSPACE_EXPERIMENT_KIND

    head = frontmatter.read_head(LocalFS(), root / rel_path / INDEX_FILENAME)
    if not head or head.get("type") != WORKSPACE_EXPERIMENT_KIND:
        return None
    found = head.get("id")
    return found if isinstance(found, str) else None


def preview_workflow_script(script: Path, root: Path) -> list[dict[str, JSONValue]]:
    """Import *script* under a scratch root and report every bound experiment."""
    from molab.entry import load_workspaces
    from molab.workflow import default_binding_registry
    from molab.workflow.dry_run import report_from_compiled
    from molab.workspace import Workspace
    from molab.workspace.workspace import set_cli_root_override

    reports: list[dict[str, JSONValue]] = []
    existing = Workspace(root)
    structure = [
        (project.name, [exp.name for exp in project.list_experiments()])
        for project in existing.list_projects()
    ]
    with tempfile.TemporaryDirectory(prefix="molab-dry-run-") as scratch:
        # Valid source scripts may use get_project/get_experiment. Mirror only
        # these empty hosts; copying historical runs would pollute the sweep.
        preview = Workspace(scratch)
        preview.materialize()
        for project_name, experiment_names in structure:
            project = preview.add_project(project_name)
            for experiment_name in experiment_names:
                project.add_experiment(experiment_name)
        set_cli_root_override(scratch, explicit=True)
        try:
            workspaces = load_workspaces(script)
        except Exception as exc:
            raise ValueError(f"Error importing {script.name}: {exc}") from exc
        finally:
            set_cli_root_override(None)
        for ws in workspaces:
            for project in ws.list_projects():
                for exp in project.list_experiments():
                    compiled = default_binding_registry.for_experiment(exp)
                    if compiled is None:
                        continue
                    rel_path = Path(str(exp.resolve())).relative_to(Path(str(ws.root))).as_posix()
                    report = report_from_compiled(
                        compiled,
                        experiment={
                            "id": _existing_experiment_id(root, rel_path),
                            "name": exp.metadata.name,
                            "path": rel_path,
                        },
                        runs=[run.parameters for run in exp.declared_runs()],
                    )
                    report.update(
                        source="code", workflow_hash=compiled.workflow_hash, entrypoint=str(script)
                    )
                    reports.append(report)
                    default_binding_registry.unbind(exp)
    if not workspaces:
        raise ValueError("No me.entry() call found in script. Add me.entry(workspace).")
    return reports


if __name__ == "__main__":
    import sys
    from contextlib import redirect_stdout

    with redirect_stdout(sys.stderr):
        reports = preview_workflow_script(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(reports, ensure_ascii=False))
