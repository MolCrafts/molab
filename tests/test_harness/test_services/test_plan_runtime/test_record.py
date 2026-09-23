"""Plan record writers bind Observation / Finding / Report."""

from __future__ import annotations

import inspect

from molab.harness.services.plan_runtime import record as rec


class TestRecordWriters:
    def test_experiment_record_is_observation(self) -> None:
        src = inspect.getsource(rec.write_experiment_record)
        assert "of=Observation" in src
        assert "Decision" not in src

    def test_finding_locates_the_observation_through_folder_and_refs_it(self) -> None:
        src = inspect.getsource(rec.write_finding_record)
        assert "get_folder" not in src
        assert "Knowledge.open" in src
        assert "knowledge_dir" not in src
        assert "append_link" not in src
        assert "folder(experiment, f" in src
        assert 'item.ref(observation, role="references")' in src

    def test_failed_plan_is_write_report_record(self) -> None:
        assert hasattr(rec, "write_report_record")
        assert not hasattr(rec, "write_failure_analysis_record")
        src = inspect.getsource(rec.write_report_record)
        assert "of=Report" in src

    def test_record_module_writes_knowledge_through_molab_knowledge(self) -> None:
        src = inspect.getsource(rec)
        assert "molab.workspace.knowledge_write" not in src
        assert "molab.workspace.knowledge" not in src
        assert "from molab.knowledge.write import write_knowledge" in src
        plan_book = inspect.getsource(rec.write_plan_book)
        assert "from molab.knowledge import PLAN_BOOK_NAME, Plan, SourceRef" in plan_book
        assert "from molab.knowledge.write import write_knowledge" in plan_book
