"""Goldens for knowledge-unify-04-cli."""

from __future__ import annotations

import inspect

from molab.cli import knowledge_cmd
from molab.cli.workspace import resources


def main() -> None:
    cmd_src = inspect.getsource(knowledge_cmd)
    assert "Bundle" not in cmd_src
    assert "from molab.knowledge import Knowledge" in cmd_src
    assert "from molab.knowledge import Concept" not in cmd_src
    assert "from molab.workspace import Bundle" not in cmd_src
    assert "Knowledge(ws_root).search" in cmd_src
    assert "Knowledge.open" in cmd_src

    harvest_src = inspect.getsource(resources.run_harvest)
    assert '{"Finding": Finding, "Observation": Observation, "Report": Report}' in harvest_src
    assert '= "Finding"' in harvest_src

    analyze_src = inspect.getsource(resources.run_analyze_failure)
    assert "Report:" in analyze_src
    assert "FailureAnalysis" not in analyze_src


if __name__ == "__main__":
    main()
