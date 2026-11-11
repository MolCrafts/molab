import { describe, expect, it } from "@rstest/core";
import { parseDocBlocks } from "./doc/blocks";
import {
  DOC_RECORD,
  DOC_SKELETON,
  fillSkeleton,
  isSourcedClass,
  runsForHost,
  toHtmlBody,
} from "./docTemplates";

describe("DOC_SKELETON", () => {
  it("starts each class from its v3 template and leaves Note empty", () => {
    expect(DOC_SKELETON.Note).toBe("");
    expect(DOC_SKELETON.Finding).toContain('!!! success "Claim"');
    expect(DOC_SKELETON.Todo).toContain("::molab-todo-list");
    expect(DOC_SKELETON.Delegation).toContain("::molab-approval");
    expect(DOC_SKELETON.Hypothesis).toContain('!!! question "Claim"');
    expect(DOC_SKELETON.Decision).toContain("## Decided by");
    expect(DOC_RECORD.Hypothesis).toEqual({ verdict: "open" });
    expect(DOC_RECORD.Decision).toEqual({ status: "made" });
    expect(isSourcedClass("Hypothesis")).toBe(true);
    expect(isSourcedClass("Decision")).toBe(true);
    expect(Object.values(DOC_SKELETON).some((body) => /^# /m.test(body))).toBe(false);
    expect(isSourcedClass("Finding")).toBe(true);
    expect(isSourcedClass("Note")).toBe(false);
  });
});

describe("fillSkeleton", () => {
  it("names the source run on bare run lines and fills the citation", () => {
    const body = fillSkeleton(`${DOC_SKELETON.Report}\n${DOC_SKELETON.Literature}`, {
      sourceRef: "molab:run/r1",
      citation: { title: "Verlet integrators, revisited", year: "2015", doi: "" },
    });
    expect(body).toContain("::molab-run-ref{ref=molab:run/r1}");
    expect(body).toContain("::molab-log{run=molab:run/r1}");
    expect(body).toContain('::molab-citation{title="Verlet integrators, revisited" year=2015}');
  });

  it("leaves lines it cannot complete alone", () => {
    expect(fillSkeleton("::molab-run-ref", {})).toBe("::molab-run-ref");
  });
});

describe("runsForHost", () => {
  const runs = [
    { id: "r1", name: "cool", path: "projects/p/experiments/e/runs/cool", ref: "molab:run/r1" },
    { id: "r2", name: "heat", path: "projects/p/experiments/other/runs/heat", ref: "molab:run/r2" },
    { id: "r3", name: "bare", path: "projects/p/experiments/e/runs/bare" },
  ];

  it("keeps runs under the host and drops a run with no ref", () => {
    expect(runsForHost(runs, "projects/p/experiments/e").map((run) => run.id)).toEqual(["r1"]);
  });

  it("returns every referenced run when the host is the workspace root", () => {
    expect(runsForHost(runs, "").map((run) => run.id)).toEqual(["r1", "r2"]);
  });
});

describe("toHtmlBody", () => {
  it("wraps prose and turns component lines into elements the page parses back", () => {
    const html = toHtmlBody(
      '::molab-todo-list\n\n## Notes\n\nUse "seeds".\n\n::molab-run-ref{ref=molab:run/r1 label="a b"}',
    );
    expect(html).toBe(
      [
        "<molab-todo-list></molab-todo-list>",
        "<molab-markdown>",
        "## Notes",
        "",
        'Use "seeds".',
        "</molab-markdown>",
        '<molab-run-ref ref="molab:run/r1" label="a b"></molab-run-ref>',
      ].join("\n"),
    );
    const components = parseDocBlocks(html).filter((block) => block.kind === "component");
    expect(components.map((block) => (block.kind === "component" ? block.attrs : null))).toEqual([
      {},
      { ref: "molab:run/r1", label: "a b" },
    ]);
  });
});
