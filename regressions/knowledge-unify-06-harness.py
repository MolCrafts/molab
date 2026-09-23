"""Goldens for knowledge-unify-06-harness."""

from __future__ import annotations

import inspect

from molab.harness.agent import harvest as harvest_mod
from molab.harness.services.plan_runtime import record as rec
from molab.harness.stages.assemble_knowledge_context import _CLASS_ORDER
from molab.knowledge import Finding, Report


def main() -> None:
    assert _CLASS_ORDER[0] is Report
    assert _CLASS_ORDER[1] is Finding
    src = inspect.getsource(harvest_mod.harvest_session)
    assert "cls:" not in src
    assert "of=Finding" in src
    finding_src = inspect.getsource(rec.write_finding_record)
    assert "get_folder" not in finding_src
    assert "Knowledge.open" in finding_src
    assert "append_link" in finding_src
    assert not hasattr(rec, "write_failure_analysis_record")
    assert "of=Report" in inspect.getsource(rec.write_report_record)


if __name__ == "__main__":
    main()
