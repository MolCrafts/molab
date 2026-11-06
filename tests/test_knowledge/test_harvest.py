"""``molab.knowledge.harvest`` — a terminal Run's outcome as typed knowledge.

Harvesting is interpretation, not archival: the two preconditions (a terminal
run, a non-empty narrative) **raise**, and the body is that narrative. Status,
errors and result values stay on the run and on the assets it registered. A
``results`` entry is a span on one of those assets. The default name is keyed
on the run, so re-harvesting the same run and kind updates one document in
place; an explicit ``name=`` allows a second take.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from molab.knowledge import Finding, Knowledge, Observation, Report
from molab.workspace.refs import ref_of

_NARRATIVE = "Mobility rises monotonically with temperature."


def _prose(body: str) -> str:
    """The narrative. Trailing ``- [@…]`` lines are the source edges."""
    lines = body.splitlines()
    while lines and (not lines[-1].strip() or lines[-1].startswith("- [@")):
        lines.pop()
    return "\n".join(lines).strip()


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
        reopened = Observation(item.path)

        assert isinstance(reopened, Observation)
        assert [(s.kind, s.ref) for s in reopened.sources] == [
            ("run", str(ref_of(run))),
            ("experiment", str(ref_of(experiment))),
        ]
        text = item.path.read_text()
        assert "created_by: tester" in text
        assert "\nsources:" not in text

    def test_body_is_the_narrative(self, run: Any) -> None:
        with run.start() as ctx:
            ctx.register({"mobility": 0.42}, title="metrics")

        item = _harvest(run, results={"mobility": 0.42})
        body = item.read()

        assert _prose(body) == _NARRATIVE
        assert "succeeded" not in body
        assert "seed" not in body
        assert "0.42" not in body
        assert "#/mobility" in body
        assert [source.span for source in item.sources if source.kind == "asset"] == ["/mobility"]

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

    def test_a_failed_run_is_harvestable_without_copying_the_error(self, run: Any) -> None:
        _fail(run, "thermostat diverged")

        item = _harvest(run, of=Report, narrative="Timestep too large.")

        assert _prose(item.read()) == "Timestep too large."
        assert "thermostat diverged" not in item.read()
        assert any(source.kind == "run" for source in item.sources)


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

    def test_a_result_with_no_registered_asset_is_refused(self, experiment: Any, run: Any) -> None:
        _succeed(run)

        with pytest.raises(ValueError, match="trace"):
            _harvest(run, results={"trace": "x" * 1000})

        assert _landed(experiment) == []


class TestHarvestCitation:
    def test_a_json_field_is_the_span_and_the_next_inputs(self, run: Any) -> None:
        with run.start() as ctx:
            ctx.register({"loss": 0.08, "epoch": 3}, title="metrics")

        item = _harvest(run, of=Finding, results={"loss": 0.08, "epoch": 3}, name="pinned")

        asset_sources = [source for source in item.sources if source.kind == "asset"]
        assert [source.span for source in asset_sources] == ["/loss", "/epoch"]
        assert item.read_cited("/loss") == 0.08
        assert item.read_cited("/epoch") == 3
        assert item.inputs == (asset_sources[0].ref.removeprefix("molab:asset/"),)
        reopened = Finding(item.path)
        assert reopened.read_cited("/loss") == 0.08

    def test_a_series_object_pins_the_step(self, run: Any) -> None:
        with run.start() as ctx:
            ctx.register(
                {"loss": [{"step": 1000, "value": 0.2}, {"step": 10000, "value": 0.08}]},
                title="curve",
            )

        item = _harvest(run, results={"loss": 0.08})

        assert [source.span for source in item.sources if source.kind == "asset"] == ["loss@10000"]
        assert item.read_cited("loss@10000") == 0.08

    def test_a_jsonl_series_pins_the_step(self, run: Any) -> None:
        with run.start() as ctx:
            ctx.register(
                '{"k":"loss","s":1000,"v":0.2}\n{"k":"loss","s":10000,"v":0.08}\n',
                title="series",
            )

        item = _harvest(run, results={"loss": 0.08})

        assert item.read_cited("loss@10000") == 0.08
        assert item.inputs == tuple(
            source.ref.removeprefix("molab:asset/")
            for source in item.sources
            if source.kind == "asset"
        )

    def test_a_sibling_attempt_id_is_not_an_input(self, experiment: Any, run: Any) -> None:
        with run.start() as ctx:
            own = ctx.register({"loss": 0.08}, title="metrics")
        other = experiment.add_run()
        with other.start() as ctx:
            ctx.register({"note": "elsewhere"}, title="other")

        item = _harvest(run, results={"loss": 0.08})

        assert item.inputs == (own.id,)

    def test_a_missing_point_is_refused_and_writes_nothing(self, experiment: Any, run: Any) -> None:
        with run.start() as ctx:
            ctx.register({"loss": 0.08}, title="metrics")

        with pytest.raises(ValueError, match="loss"):
            _harvest(run, results={"loss": 0.09})

        assert _landed(experiment) == []

    def test_two_assets_with_the_same_point_are_refused(self, run: Any) -> None:
        with run.start() as ctx:
            ctx.register({"loss": 0.08, "tag": "a"}, title="a")
            ctx.register({"loss": 0.08, "tag": "b"}, title="b")

        with pytest.raises(ValueError, match="more than one"):
            _harvest(run, results={"loss": 0.08})

    def test_two_steps_with_the_same_value_are_refused(self, run: Any) -> None:
        with run.start() as ctx:
            ctx.register(
                '{"k":"loss","s":1000,"v":0.08}\n{"k":"loss","s":2000,"v":0.08}\n',
                title="flat",
            )

        with pytest.raises(ValueError, match="more than one point"):
            _harvest(run, results={"loss": 0.08})

    def test_registered_assets_without_results_stay_unspanned(self, run: Any) -> None:
        with run.start() as ctx:
            asset = ctx.register({"loss": 0.08}, title="metrics")

        item = _harvest(run)

        assert [(source.ref, source.span) for source in item.sources if source.kind == "asset"] == [
            (asset.ref, None)
        ]
        assert item.inputs == (asset.id,)

    def test_an_empty_span_is_refused(self, run: Any) -> None:
        with run.start() as ctx:
            ctx.register({"loss": 0.08}, title="metrics")

        item = _harvest(run, results={"loss": 0.08})

        with pytest.raises(ValueError, match="requires a span"):
            item.read_cited("")

    def test_a_span_that_is_not_one_citation_is_refused(self, run: Any) -> None:
        with run.start() as ctx:
            ctx.register({"loss": 0.08}, title="metrics")

        item = _harvest(run, results={"loss": 0.08})

        with pytest.raises(ValueError, match="not one asset citation"):
            item.read_cited("/missing")


def test_citation_reads_are_document_members() -> None:
    import molab.knowledge.harvest as harvest

    assert not hasattr(harvest, "cited_inputs")
    assert not hasattr(harvest, "read_cited")
    assert "cited_inputs" not in harvest.__all__
    assert "read_cited" not in harvest.__all__
