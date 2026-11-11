import { describe, expect, it } from "@rstest/core";
import { showcaseKnowledgeEdges } from "../knowledge-links";

const path = "projects/p/knowledges/report.md";
const target = "projects/p/knowledges/source.md";
const notes = (body: string) =>
  new Map([
    [path, { relPath: path, body }],
    [target, { relPath: target, body: "" }],
  ]);

describe("showcase typed knowledge links", () => {
  it("resolves relative/fragment links, deduplicates each role, preserves different roles", () => {
    expect(
      showcaseKnowledgeEdges(
        notes(
          "[@derived_from origin](source.md#result)\n[@supports evidence](source.md)\n[@derived_from again](source.md)",
        ),
      ),
    ).toEqual([
      { source: path, target, role: "derived_from", kind: "document" },
      { source: path, target, role: "supports", kind: "document" },
    ]);
  });

  it("classifies entity refs, external sources and missing files; skips fenced examples", () => {
    const edges = showcaseKnowledgeEdges(
      notes(
        "[@records run](molab:experiment/e/run/r)\n[@cites paper](https://example.org/paper)\n[old](gone.md)\n```md\n[@derived_from example](source.md)\n```\n`[example](source.md)`",
      ),
    );
    expect(edges.map((edge) => [edge.role, edge.kind])).toEqual([
      ["records", "ref"],
      ["cites", "external"],
      ["references", "missing"],
    ]);
    expect(edges[2].target).toBe("projects/p/knowledges/gone.md");
  });
});
