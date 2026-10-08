"""``molab.knowledge.harvest`` — a terminal Run's outcome as typed knowledge.

Harvesting is interpretation, not archival: the two preconditions (a terminal
run, a non-empty narrative) **raise**, and the body renders the run's status,
params and results so the document reads without opening ``run.json``. The
default name is keyed on the run, so re-harvesting the same run and kind updates
one document in place; an explicit ``name=`` allows a second take.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from molab.knowledge import Finding, Knowledge, Observation, Report
from molab.workspace.refs import ref_of

_NARRATIVE = "Mobility rises monotonically with temperature."


def _succeed(run: Any) -> None:
    """Drive *run* to the ``succeeded`` terminal via the real lifecycle."""
    with run.start():
        pass


def _fail(run: Any, message: str) -> None:
    """Drive *run* to the ``failed`` terminal, recording *message* as the error."""
    with run.start() as ctx:
        ctx.mark_failed(message)


def _harvest(run: Any, **overrides: Any) -> Knowledge:
    of = overrides.pop("of", Observation)
    kwargs: dict[str, Any] = {"narrative": _NARRATIVE, "created_by": "tester"}
    kwargs.update(overrides)
    return of.harvest(run, **kwargs)


def _landed(experiment: Any) -> list[str]:
    container = Path(str(experiment.resolve())) / "knowledges"
    return sorted(p.name for p in container.iterdir()) if container.is_dir() else []


class TestHarvestRun:
    def test_returns_the_requested_class_under_the_experiments_knowledges(
        self, experiment: Any, run: Any
    ) -> None:
        _succeed(run)

        item = _harvest(run)

        assert isinstance(item, Observation)
        assert run.id in item.name, "the default name is keyed on the run"
        assert Path(item.path).parent == Path(str(experiment.resolve())) / "knowledges"

    def test_head_carries_the_run_and_experiment_sources(self, experiment: Any, run: Any) -> None:
        _succeed(run)

        item = _harvest(run)
        reopened = Knowledge.open(item.path)

        assert isinstance(reopened, Observation)
        assert [(s.kind, s.ref) for s in reopened.sources] == [
            ("run", str(ref_of(run))),
            ("experiment", str(ref_of(experiment))),
        ]
        text = item.path.read_text()
        assert "created_by: tester" in text
        assert "\nsources:" not in text

    def test_body_renders_narrative_status_params_and_results(self, run: Any) -> None:
        _succeed(run)

        body = _harvest(run, results={"mobility": 0.42}).read()

        assert _NARRATIVE in body
        assert "succeeded" in body
        assert "seed" in body
        assert "0.42" in body
        assert f"# [Observation] run {run.id}" in body

    def test_writes_a_derived_from_edge_to_the_run(self, run: Any) -> None:
        _succeed(run)

        edges = [edge for edge in _harvest(run).links() if edge.role == "derived_from"]

        assert [edge.target for edge in edges] == [str(ref_of(run)), str(ref_of(run.experiment))]

    def test_the_default_name_re_harvests_in_place(self, experiment: Any, run: Any) -> None:
        _succeed(run)

        first = _harvest(run, narrative="First take.")
        second = _harvest(run, narrative="Second take: refined interpretation.")

        assert second.name == first.name
        assert _landed(experiment) == [f"{first.name}.md"]
        assert "Second take" in second.read()
        assert "First take." not in second.read()

    def test_an_explicit_name_allows_a_second_harvest(self, experiment: Any, run: Any) -> None:
        _succeed(run)

        _harvest(run)
        named = _harvest(run, of=Finding, name="finding-take-2", narrative="A second angle.")

        assert named.name == "finding-take-2"
        assert len(_landed(experiment)) == 2

    def test_a_failed_run_is_harvestable_and_carries_the_error(self, run: Any) -> None:
        _fail(run, "thermostat diverged")

        body = _harvest(run, of=Report, narrative="Timestep too large.").read()

        assert "failed" in body
        assert "thermostat diverged" in body


class TestHarvestPreconditions:
    def test_a_non_terminal_run_is_refused(self, run: Any) -> None:
        with pytest.raises(ValueError, match="only a terminal run"):
            _harvest(run)

        with run.start(), pytest.raises(ValueError, match="only a terminal run"):
            _harvest(run)

    @pytest.mark.parametrize("narrative", ["", "   \n"])
    def test_a_blank_narrative_is_refused(self, run: Any, narrative: str) -> None:
        _succeed(run)

        with pytest.raises(ValueError, match="non-empty narrative"):
            _harvest(run, narrative=narrative)

    def test_a_result_value_is_truncated_at_the_cap(self, run: Any) -> None:
        _succeed(run)

        body = _harvest(run, results={"trace": "x" * 1000}).read()

        assert "x" * 401 not in body, "a 1000-char value must not land verbatim"
        assert "x" * 100 in body, "a truncated prefix of the value must survive"
        # repr("x" * 1000) is 1002 chars: 400 kept, the remaining 602 counted.
        assert "… (+602 chars)" in body
