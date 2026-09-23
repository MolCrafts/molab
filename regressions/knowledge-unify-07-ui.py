"""Goldens for knowledge-unify-07-ui: generated client six-class contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "apps" / "web" / "src" / "api" / "generated"
CLASS_TS = ROOT / "apps" / "web" / "src" / "plugins" / "knowledge" / "knowledgeClass.ts"


def main() -> None:
    class_src = CLASS_TS.read_text(encoding="utf-8")
    for name in ("Note", "Literature", "Report", "Finding", "Plan", "Observation"):
        assert name in class_src
    assert "FailureAnalysis" not in class_src
    assert "ReferenceConcept" not in class_src
    for head in (
        "note.json",
        "literature.json",
        "report.json",
        "finding.json",
        "plan.json",
        "observation.json",
    ):
        assert head in class_src

    harvest = (GENERATED / "models" / "RunHarvestRequest.ts").read_text(encoding="utf-8")
    for name in ("Note", "Literature", "Report", "Finding", "Plan", "Observation"):
        assert name in harvest
    assert "FailureAnalysis" not in harvest
    assert "ReferenceConcept" not in harvest
    text = ""
    for path in (ROOT / "apps" / "web" / "src" / "plugins" / "knowledge").rglob("*.ts*"):
        text += path.read_text(encoding="utf-8")
    assert "ReferenceConcept" not in text
    assert "FailureAnalysis" not in text


if __name__ == "__main__":
    main()
