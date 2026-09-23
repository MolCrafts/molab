"""Goldens for knowledge-unify-05-server."""

from __future__ import annotations

import inspect
from typing import get_args

from molab.server.routes import knowledge as knowledge_routes
from molab.server.routes import run as run_routes
from molab.server.schemas.requests import RunHarvestRequest


def main() -> None:
    list_src = inspect.getsource(knowledge_routes.list_knowledge)
    search_src = inspect.getsource(knowledge_routes.search_knowledge)
    get_src = inspect.getsource(knowledge_routes.get_note)
    assert ".walk()" in list_src
    assert ".search(" in search_src
    assert "Knowledge.open" in get_src
    assert "bundle.notes" not in list_src
    assert "_bundle(workspace).search" not in search_src

    values = set(get_args(RunHarvestRequest.model_fields["cls"].annotation))
    assert values == {
        "Note",
        "Literature",
        "Report",
        "Finding",
        "Plan",
        "Observation",
    }
    assert "kind" not in RunHarvestRequest.model_fields

    harvest_src = inspect.getsource(run_routes.harvest_run_route)
    assert "is not a harvest target" in harvest_src
    analyze_src = inspect.getsource(run_routes.analyze_run_failure_route)
    assert "FailureAnalysis" not in analyze_src
    from molab.server.schemas import requests as reqs

    assert "FailureAnalysis" not in inspect.getsource(reqs)


if __name__ == "__main__":
    main()
