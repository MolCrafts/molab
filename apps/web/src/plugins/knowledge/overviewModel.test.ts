import { describe, expect, it } from "@rstest/core";
import type { NoteSummary } from "@/api/generated/models/NoteSummary";
import { byRecent, knowledgeOverview, writingDays } from "./overviewModel";

const note = (cls: string, name: string): NoteSummary => ({
  cls,
  name,
  relPath: `knowledges/${name}.md`,
  hostPath: "",
  excerpt: "",
});

describe("knowledgeOverview", () => {
  const notes = [
    note("Todo", "todo"),
    note("Milestone", "met"),
    note("Milestone", "open"),
    note("Delegation", "check"),
    note("Note", "plain"),
  ];
  const records = new Map<string, unknown>([
    [
      "knowledges/todo.md",
      {
        items: [
          { id: "a", title: "Prepare", status: "done" },
          { id: "b", title: "Bind", status: "open" },
          { id: "c", title: "Compare", status: "blocked" },
        ],
      },
    ],
    ["knowledges/met.md", { stage: "s", criterion: "c1", status: "met" }],
    ["knowledges/open.md", { stage: "s", criterion: "c2", status: "open" }],
    [
      "knowledges/check.md",
      { goal: "g", scope: "s", state: "blocked", questions: ["Run 4 jobs?"] },
    ],
  ]);
  const overview = knowledgeOverview(notes, records);

  it("says what blocks the work", () => {
    expect(overview.verdict).toEqual({
      status: "interrupted",
      subject: "1 blocked todo · 1 delegation waits for you",
      evidence: "Compare — blocked · todo",
    });
  });

  it("counts todos and milestones", () => {
    expect(overview.todos).toEqual({ done: 1, open: 1, blocked: 1 });
    expect(overview.milestoneMet).toBe(1);
    expect(overview.milestoneTotal).toBe(2);
    expect(overview.milestones.succeeded).toBe(1);
    expect(overview.milestones.queued).toBe(1);
  });

  it("lists open work, blocked first", () => {
    expect(overview.openWork.map((row) => [row.status, row.title])).toEqual([
      ["interrupted", "Compare"],
      ["interrupted", "Run 4 jobs?"],
      ["pending", "Bind"],
      ["pending", "open"],
    ]);
  });

  it("counts documents per class in class order", () => {
    expect(overview.byClass.map((row) => [row.cls, row.count])).toEqual([
      ["Note", 1],
      ["Todo", 1],
      ["Milestone", 2],
      ["Delegation", 1],
    ]);
  });

  it("has a quiet verdict for an empty workspace and for nothing open", () => {
    expect(knowledgeOverview([], new Map()).verdict.subject).toBe("No documents yet");
    expect(knowledgeOverview([note("Note", "n")], new Map()).verdict).toEqual({
      status: "succeeded",
      subject: "Nothing open",
      evidence: null,
    });
  });
});

describe("writingDays / byRecent", () => {
  const now = new Date(2026, 10, 9, 12).getTime();
  const at = (daysAgo: number): string => new Date(now - daysAgo * 86_400_000).toISOString();

  it("counts last edits per day, oldest day first, zeros kept", () => {
    const days = writingDays(
      [{ updatedAt: at(0) }, { updatedAt: at(0) }, { updatedAt: at(2) }, {}],
      now,
      3,
    );
    expect(days.map((d) => d.edits)).toEqual([1, 0, 2]);
    expect(days).toHaveLength(3);
  });

  it("puts the newest edit first and undated documents last", () => {
    const rows = [
      { name: "b", updatedAt: at(3) },
      { name: "a", updatedAt: null },
      { name: "c", updatedAt: at(1) },
    ];
    expect(byRecent(rows).map((row) => row.name)).toEqual(["c", "b", "a"]);
  });
});
