import { describe, expect, it } from "@rstest/core";
import { AgentRef } from "@/api/generated/models/AgentRef";
import type { DocumentHistory } from "@/api/generated/models/DocumentHistory";
import type { DocumentVersion } from "@/api/generated/models/DocumentVersion";
import {
  diffLineTone,
  latestVersion,
  versionAgent,
  versionEvent,
  versionSwitcherLabel,
  versionToOpen,
} from "./knowledgeVersions";

const version = (number: number, extra: Partial<DocumentVersion> = {}): DocumentVersion => ({
  number,
  commit: `${number}`.repeat(40),
  path: "knowledges/report.md",
  occurred_at: "2026-11-10T09:21:04Z",
  summary: "report",
  ...extra,
});

const history = (uncommitted: boolean): DocumentHistory => ({
  available: true,
  uncommitted,
  versions: [
    version(3, {
      event: "knowledge.rewritten",
      agent: { id: "molab", type: AgentRef.type.SYSTEM, name: "Molab" },
    }),
    version(2),
    version(1, { event: "knowledge.fields_replaced" }),
  ],
});

describe("knowledge versions", () => {
  it("names the event, or a manual commit without one", () => {
    const [v3, v2, v1] = history(false).versions;
    expect(versionEvent(v3)).toBe("rewritten");
    expect(versionEvent(v2)).toBe("manual commit");
    expect(versionEvent(v1)).toBe("fields replaced");
    expect(versionAgent(v3)).toBe("Molab");
    expect(versionAgent(v2)).toBe("");
  });

  it("opens the newest version of a clean file as the live page", () => {
    expect(versionToOpen(history(false), 3)).toBeNull();
    expect(versionToOpen(history(false), 2)).toBe(2);
    // With uncommitted edits the newest version differs from the page.
    expect(versionToOpen(history(true), 3)).toBe(3);
  });

  it("labels the latest, the working copy and an old version", () => {
    expect(latestVersion(history(false))).toBe(3);
    expect(latestVersion({ available: true, versions: [] })).toBeNull();
    expect(versionSwitcherLabel(history(false), null)).toBe("v3 · latest");
    expect(versionSwitcherLabel(history(true), null)).toBe("Working copy");
    expect(versionSwitcherLabel(history(false), 1)).toBe("v1 of 3");
  });

  it("reads diff lines without counting file headers as changes", () => {
    expect(diffLineTone("--- a@v1")).toBe("context");
    expect(diffLineTone("+++ b (working copy)")).toBe("context");
    expect(diffLineTone("@@ -1 +1 @@")).toBe("hunk");
    expect(diffLineTone("+added")).toBe("added");
    expect(diffLineTone("-removed")).toBe("removed");
    expect(diffLineTone(" same")).toBe("context");
  });
});
