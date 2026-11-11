/** Pure reads behind `<molab-stage-track>`: which roadmap, and each stage's glyph and line. */

import type { CampaignProgress, StageProgress } from "../../campaignProgress";

export type StageGlyph = "succeeded" | "running" | "interrupted" | "failed" | "pending";

/** Met / Done → succeeded; Blocked → interrupted; some todos done → running. */
export const stageGlyph = (stage: StageProgress): StageGlyph => {
  if (stage.word === "Met" || stage.word === "Done") return "succeeded";
  if (stage.word === "Missed") return "failed";
  if (stage.word === "Blocked") return "interrupted";
  if (stage.todos.done > 0) return "running";
  return "pending";
};

/** "2 of 3 todos" / "blocked" / "met" / "not started". */
export const stageLine = (stage: StageProgress): string => {
  if (stage.word === "Blocked") return "blocked";
  if (stage.todos.total > 0) return `${stage.todos.done} of ${stage.todos.total} todos`;
  if (stage.word === "Met") return "met";
  if (stage.word === "Missed") return "missed";
  return "not started";
};

/** Share of the stage's todos that are done, 0–1 (a met stage with none is full). */
export const stageShare = (stage: StageProgress): number => {
  if (stage.todos.total === 0) return stageGlyph(stage) === "succeeded" ? 1 : 0;
  return stage.todos.done / stage.todos.total;
};

/** The host directory a document lives on: `<host>/knowledges/<slug>.md` → `<host>`. */
export const hostOfDoc = (relPath: string): string => {
  const at = relPath.lastIndexOf("knowledges/");
  if (at < 0) return "";
  return relPath.slice(0, at).replace(/\/$/, "");
};

/** The named roadmap, else the current document when it is one, else the first. */
export const pickCampaign = (
  campaigns: readonly CampaignProgress[],
  options: { roadmap?: string; relPath: string; cls: string },
): CampaignProgress | null => {
  if (options.roadmap) {
    return campaigns.find((item) => item.roadmapPath === options.roadmap) ?? null;
  }
  if (options.cls === "Roadmap") {
    const own = campaigns.find((item) => item.roadmapPath === options.relPath);
    if (own) return own;
  }
  return campaigns[0] ?? null;
};
