"""arch-own-06d: legacy knowledge documents become canonical markdown.

Public API only. No third-party runtime.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from molab.cli.migrate_cmd import migrate_knowledge
from molab.knowledge import Knowledge
from molab.workspace import Workspace


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "lab"
        workspace = Workspace(root, name="lab")
        workspace.materialize()
        experiment = workspace.add_project("p").add_experiment("e")
        run = experiment.add_run(params={"seed": 1})
        (root / "cooling-rate.md").write_text(
            "---\nclass: Note\n---\n\n"
            "From [@derived_from run](projects/p/experiments/e/runs/seed=1).\n",
            encoding="utf-8",
        )
        obs = Path(experiment.resolve()) / "knowledges" / "obs-1"
        obs.mkdir(parents=True)
        (obs / "observation.json").write_text(
            json.dumps(
                {
                    "created_by": "alice",
                    "sources": [
                        {"kind": "run", "ref": run.id},
                        {"kind": "experiment", "ref": experiment.id},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (obs / "index.md").write_text(
            "[cooling](../../../../../../cooling-rate.md)\n",
            encoding="utf-8",
        )

        report = migrate_knowledge(root)
        obs_path = Path(experiment.resolve()) / "knowledges" / "obs-1.md"
        body = obs_path.read_text(encoding="utf-8")

        assert report.moved == [
            ("cooling-rate.md", "knowledges/cooling-rate.md"),
            (
                "projects/p/experiments/e/knowledges/obs-1",
                "projects/p/experiments/e/knowledges/obs-1.md",
            ),
        ]
        assert report.links_rewritten == 2
        assert report.sources_folded == 2
        assert report.unresolved == []
        assert report.ambiguous == []
        assert "../../../../../knowledges/cooling-rate.md" in body
        assert "sources:" not in body.split("---", 2)[1]
        assert type(Knowledge.open(obs_path)).__name__ == "Observation"
        assert migrate_knowledge(root).changed is False

    print("arch-own-06d-migrate: ok")


if __name__ == "__main__":
    main()
