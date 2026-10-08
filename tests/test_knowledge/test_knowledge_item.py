"""SourceRef maps each kind onto one markdown link and back."""

from __future__ import annotations

import pytest

from molab.knowledge.edges import Edge
from molab.knowledge.knowledge_item import SourceRef
from molab.workspace.refs import InvalidRefError, ref_of


class TestSourceRef:
    def test_run_target_and_line(self) -> None:
        source = SourceRef(kind="run", ref="molab:experiment/E1/run/R1")

        assert source.link_target("/w/k") == "molab:experiment/E1/run/R1"
        assert source.link_role == "derived_from"
        assert source.link_line("/w/k") == "- [@derived_from R1](molab:experiment/E1/run/R1)"

    def test_doi_becomes_an_https_url(self) -> None:
        source = SourceRef(kind="reference", ref="DOI:10.1000/xyz")

        assert source.link_target("/w/k") == "https://doi.org/10.1000/xyz"
        assert source.link_role == "cites"

    def test_file_target_is_relative_to_the_document_dir(self) -> None:
        source = SourceRef(kind="file", ref="/w/p/data/x.csv")

        assert source.link_target("/w/p/knowledges") == "../data/x.csv"

    def test_span_is_appended(self) -> None:
        source = SourceRef(kind="run", ref="molab:experiment/E1/run/R1", span="L3-L9")

        assert source.link_target("/w/k") == "molab:experiment/E1/run/R1#L3-L9"

    def test_bare_run_id_names_source_ref_of(self) -> None:
        source = SourceRef(kind="run", ref="R1")

        with pytest.raises(ValueError, match=r"SourceRef\.of"):
            source.link_target("/w/k")

    def test_plain_reference_text_is_rejected(self) -> None:
        source = SourceRef(kind="reference", ref="smith2024")

        with pytest.raises(ValueError):
            source.link_target("/w/k")

    def test_from_edge_round_trips_artifact_and_file(self) -> None:
        artifact = SourceRef.from_edge(
            Edge("molab:experiment/E1/run/R1/artifact/A1", "derived_from")
        )
        file_source = SourceRef.from_edge(Edge("/w/p/s1", "derived_from"))

        assert (artifact.kind, artifact.ref) == (
            "artifact",
            "molab:experiment/E1/run/R1/artifact/A1",
        )
        assert (file_source.kind, file_source.ref) == ("file", "/w/p/s1")

    def test_from_edge_rejects_a_malformed_ref(self) -> None:
        with pytest.raises(InvalidRefError):
            SourceRef.from_edge(Edge("molab:bogus", "derived_from"))

    def test_of_uses_ref_of(self, lab, run) -> None:
        project = lab.get_project("p")

        assert SourceRef.of(run).ref == str(ref_of(run))
        assert SourceRef.of(run, artifact_id="A1").kind == "artifact"
        assert SourceRef.of(project).kind == "project"
