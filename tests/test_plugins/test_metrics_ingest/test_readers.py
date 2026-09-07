"""The seam: molexp reaches a format it does not own, and never privileges one.

molexp ships no reader. molplot ships no reader. A format belongs to whatever
package can parse it, which declares a reader in the
``molcrafts.metric_readers`` entry-point group — a name with no molexp in it,
matched structurally, so the provider imports nothing from here.
"""

from __future__ import annotations

import ast
from pathlib import Path

from molexp.plugins.metrics_ingest import detect_log_formats
from molexp.plugins.metrics_ingest.readers import (
    ENTRY_POINT_GROUP,
    MetricReader,
    ReadRequest,
    apply,
    describe_readers,
    readers,
    sniff,
)


class TestTheGroupIsNeutral:
    def test_the_entry_point_group_names_molcrafts_not_molexp(self):
        assert ENTRY_POINT_GROUP == "molcrafts.metric_readers"
        assert "molexp" not in ENTRY_POINT_GROUP

    def test_molexp_ships_no_reader_of_its_own(self):
        """Every reader arrives from the package that owns its format.

        molexp may define the *contract* (a Protocol) but never an
        implementation — shipping one would make that format the privileged
        default and put a parser back inside the platform.
        """
        package = Path(detect_log_formats.__module__.replace(".", "/")).parent
        root = Path(__file__).resolve().parents[3] / "src" / package
        offenders = []
        for source in sorted(root.glob("*.py")):
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.ClassDef) or not node.name.endswith("Reader"):
                    continue
                bases = {getattr(base, "id", getattr(base, "attr", "")) for base in node.bases}
                if "Protocol" in bases:  # the contract, not an implementation
                    continue
                offenders.append(f"{source.name}:{node.lineno} {node.name}")
        assert not offenders, f"molexp defines readers: {offenders}"


class TestRegisteredFormats:
    def test_a_registered_reader_satisfies_the_protocol(self):
        assert all(isinstance(reader, MetricReader) for reader in readers())

    def test_a_format_molexp_never_heard_of_is_discovered(self, fake_run):
        hits = detect_log_formats(fake_run)
        assert [hit.format for hit in hits] == ["fake_sim_log"]

    def test_sniff_returns_the_claiming_reader(self, fake_run):
        reader = sniff(next(fake_run.glob("*.fakelog")))
        assert reader is not None
        assert reader.format == "fake_sim_log"

    def test_an_unclaimed_file_is_left_alone(self, tmp_path):
        (tmp_path / "notes.md").write_text("# notes", encoding="utf-8")
        assert sniff(tmp_path / "notes.md") is None
        assert detect_log_formats(tmp_path) == []

    def test_describe_carries_the_client_facing_hints(self):
        described = {entry["format"]: entry for entry in describe_readers()}
        assert described["fake_sim_log"]["patterns"] == ["**/*.fakelog"]
        assert described["fake_sim_log"]["tailable"] is False


class TestTheViewerSetsTheSamplingPolicy:
    """``stride`` travels to the reader; it is not applied behind its back."""

    def test_a_reader_that_can_stride_does_it_itself(self, tmp_path):
        path = tmp_path / "series.striding"
        path.write_text("\n".join(f"k {i}" for i in range(100)), encoding="utf-8")

        reader = sniff(path)
        assert reader is not None
        records = list(reader.read(path, source="series.striding", request=ReadRequest(stride=10)))

        assert len(records) == 10
        assert [r["v"] for r in records] == [float(i) for i in range(0, 100, 10)]
        assert all(r["tags"]["strided_by_reader"] for r in records)

    def test_stride_counts_per_series_not_across_the_stream(self):
        """Records interleave by column, so striding the flat stream would
        land on one column every time and drop the others entirely."""
        stream = [
            {"t": "scalar", "k": key, "v": float(step)}
            for step in range(10)
            for key in ("Temp", "Press", "Volume")
        ]
        kept = list(apply(ReadRequest(stride=5), stream))
        assert {r["k"] for r in kept} == {"Temp", "Press", "Volume"}
        assert len(kept) == 6  # two samples of each of the three series

    def test_limit_and_type_filters_reach_the_reader(self, fake_run):
        path = next(fake_run.glob("*.fakelog"))
        reader = sniff(path)
        assert len(list(reader.read(path, source="x", request=ReadRequest(limit=1)))) == 1
        only = next(iter(reader.read(path, source="x", request=ReadRequest(keys=("temp",)))))
        assert only["k"] == "temp"
