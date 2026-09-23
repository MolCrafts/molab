"""Plan record writers bind Observation / Finding / Report."""

from __future__ import annotations

import inspect

from molab.harness.services.plan_runtime import record as rec


class TestRecordWriters:
    def test_experiment_record_is_observation(self) -> None:
        src = inspect.getsource(rec.write_experiment_record)
        assert "of=Observation" in src
        assert "Decision" not in src

    def test_finding_uses_from_dir_and_append_link(self) -> None:
        src = inspect.getsource(rec.write_finding_record)
        assert "get_folder" not in src
        assert "Knowledge.open" in src
        assert "append_link" in src

    def test_failed_plan_is_write_report_record(self) -> None:
        assert hasattr(rec, "write_report_record")
        assert not hasattr(rec, "write_failure_analysis_record")
        src = inspect.getsource(rec.write_report_record)
        assert "of=Report" in src
