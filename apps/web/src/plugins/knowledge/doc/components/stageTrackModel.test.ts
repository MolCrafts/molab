import { describe, expect, it } from "@rstest/core";
import type { CampaignProgress, StageProgress } from "../../campaignProgress";
import { hostOfDoc, pickCampaign, stageGlyph, stageLine, stageShare } from "./stageTrackModel";

const stage = (word: string, done: number, total: number, blocked = 0): StageProgress => ({
  id: word,
  title: word,
  word,
  todos: { done, total, blocked, open: total - done - blocked },
});

describe("stage glyph and line", () => {
  it("maps each stage", () => {
    expect(stageGlyph(stage("Done", 2, 2))).toBe("succeeded");
    expect(stageGlyph(stage("Met", 0, 0))).toBe("succeeded");
    expect(stageGlyph(stage("Open", 1, 3))).toBe("running");
    expect(stageGlyph(stage("Blocked", 0, 1, 1))).toBe("interrupted");
    expect(stageGlyph(stage("Open", 0, 0))).toBe("pending");
    expect(stageLine(stage("Open", 1, 3))).toBe("1 of 3 todos");
    expect(stageLine(stage("Blocked", 0, 1, 1))).toBe("blocked");
    expect(stageLine(stage("Open", 0, 0))).toBe("not started");
    expect(stageShare(stage("Open", 1, 4))).toBe(0.25);
    expect(stageShare(stage("Met", 0, 0))).toBe(1);
  });
});

describe("pickCampaign", () => {
  const campaign = (path: string): CampaignProgress => ({
    roadmapTitle: path,
    roadmapPath: path,
    planTitle: null,
    planPath: null,
    stages: [],
  });
  const all = [campaign("p/knowledges/a.md"), campaign("p/knowledges/b.md")];
  it("prefers the named roadmap, then the current one, then the first", () => {
    const named = { roadmap: "p/knowledges/b.md", relPath: "x.md", cls: "Plan" };
    expect(pickCampaign(all, named)?.roadmapPath).toBe("p/knowledges/b.md");
    expect(pickCampaign(all, { ...named, roadmap: "nope" })).toBeNull();
    expect(pickCampaign(all, { relPath: "p/knowledges/b.md", cls: "Roadmap" })?.roadmapPath).toBe(
      "p/knowledges/b.md",
    );
    expect(pickCampaign(all, { relPath: "x.md", cls: "Plan" })?.roadmapPath).toBe(
      "p/knowledges/a.md",
    );
    expect(pickCampaign([], { relPath: "x.md", cls: "Plan" })).toBeNull();
  });
  it("reads a document's host", () => {
    expect(hostOfDoc("projects/p/knowledges/a.md")).toBe("projects/p");
    expect(hostOfDoc("knowledges/a.md")).toBe("");
  });
});
