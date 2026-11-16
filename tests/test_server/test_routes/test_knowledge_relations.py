from __future__ import annotations

from pathlib import Path

from molab.knowledge.concepts import Note


def test_relation_authoring_round_trip_and_stale_write(fresh_run, served):
    workspace, _, _ = fresh_run
    root = Path(str(workspace.root))
    source, target = Note(root / "knowledges" / "source"), Note(root / "knowledges" / "target")
    source.write("# Source\n\nNarrative stays.\n", tags=["keep"])
    target.write("# Target\n")
    query = {"path": "knowledges/source.md"}
    with served(workspace) as client:
        snapshot = client.get("/api/knowledge/doc/relations", params=query).json()
        assert snapshot["relations"] == []
        added = client.patch(
            "/api/knowledge/doc/relations",
            params=query,
            json={
                "action": "add",
                "ifMatch": snapshot["digest"],
                "target": "knowledges/target.md",
                "role": "supports",
                "text": "Target evidence",
            },
        )
        assert added.status_code == 200, added.text
        current = added.json()
        assert current["relations"] == [
            {
                "id": 0,
                "target": "knowledges/target.md",
                "role": "supports",
                "label": "Target evidence",
                "kind": "document",
            }
        ]
        stale = client.patch(
            "/api/knowledge/doc/relations",
            params=query,
            json={
                "action": "remove",
                "id": 0,
                "ifMatch": snapshot["digest"],
            },
        )
        assert stale.status_code == 409
        changed = client.patch(
            "/api/knowledge/doc/relations",
            params=query,
            json={
                "action": "replace",
                "id": 0,
                "ifMatch": current["digest"],
                "role": "contradicts",
            },
        )
        assert changed.status_code == 200, changed.text
        graph = client.get("/api/knowledge/graph").json()
        assert {
            "source": query["path"],
            "target": "knowledges/target.md",
            "role": "contradicts",
            "kind": "document",
        } in graph["edges"]
        removed = client.patch(
            "/api/knowledge/doc/relations",
            params=query,
            json={
                "action": "remove",
                "id": 0,
                "ifMatch": changed.json()["digest"],
            },
        )
        assert removed.status_code == 200, removed.text
        assert removed.json()["relations"] == []
        assert "Narrative stays." in source.read()
        assert source.tags() == ["keep"]


def test_relation_authoring_rejects_escaping_targets_and_requires_digest(fresh_run, served):
    workspace, _, _ = fresh_run
    source = Note(Path(str(workspace.root)) / "knowledges" / "source")
    source.write("# Source\n")
    with served(workspace) as client:
        query = {"path": "knowledges/source.md"}
        snapshot = client.get("/api/knowledge/doc/relations", params=query).json()
        for target in ["../outside.md", "/tmp/outside.md", "molab:invalid/ref", "missing.md"]:
            response = client.patch(
                "/api/knowledge/doc/relations",
                params=query,
                json={
                    "action": "add",
                    "target": target,
                    "ifMatch": snapshot["digest"],
                },
            )
            assert response.status_code == 422, response.text
        assert (
            client.patch(
                "/api/knowledge/doc/relations",
                params=query,
                json={
                    "action": "remove",
                    "id": 0,
                },
            ).status_code
            == 422
        )
        assert (
            client.get("/api/knowledge/doc/relations", params={"path": "../outside.md"}).status_code
            == 422
        )
