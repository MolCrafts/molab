/** Structured fields for Roadmap, Todo, and Milestone. The narrative stays separate. */

export const PLANNING_CLASSES = ["Roadmap", "Todo", "Milestone"] as const;

export type PlanningClass = (typeof PLANNING_CLASSES)[number];

export const isPlanningClass = (cls: string): cls is PlanningClass =>
  (PLANNING_CLASSES as readonly string[]).includes(cls);

export type TodoStatus = "open" | "done" | "blocked";
export type MilestoneStatus = "open" | "met" | "missed";

export const TODO_STATUSES: readonly TodoStatus[] = ["open", "done", "blocked"];
export const MILESTONE_STATUSES: readonly MilestoneStatus[] = ["open", "met", "missed"];

export interface StageDraft {
  key: string;
  id: string;
  title: string;
  experiment: string;
  depends: string;
}

export interface TodoDraft {
  key: string;
  id: string;
  title: string;
  status: TodoStatus;
  stage: string;
}

export interface MilestoneDraft {
  stage: string;
  criterion: string;
  status: MilestoneStatus;
}

export interface PlanningDraft {
  stages: StageDraft[];
  items: TodoDraft[];
  milestone: MilestoneDraft;
}

const rowKey = (): string =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `row-${Math.random().toString(36).slice(2)}`;

export const emptyStage = (): StageDraft => ({
  key: rowKey(),
  id: "",
  title: "",
  experiment: "",
  depends: "",
});

export const emptyTodo = (): TodoDraft => ({
  key: rowKey(),
  id: "",
  title: "",
  status: "open",
  stage: "",
});

export const emptyPlanningDraft = (): PlanningDraft => ({
  stages: [emptyStage()],
  items: [emptyTodo()],
  milestone: { stage: "", criterion: "", status: "open" },
});

const splitIds = (text: string): string[] =>
  text
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export type PlanningBuild =
  | { ok: true; record: Record<string, unknown> }
  | { ok: false; message: string };

const clash = (ids: string[], message: string): PlanningBuild | null =>
  new Set(ids).size === ids.length ? null : { ok: false, message };

export const buildPlanningRecord = (cls: PlanningClass, draft: PlanningDraft): PlanningBuild => {
  if (cls === "Roadmap") {
    const filled = draft.stages.filter(
      (row) => row.id.trim() || row.title.trim() || row.experiment.trim() || row.depends.trim(),
    );
    if (filled.length === 0 || filled.some((row) => !row.id.trim() || !row.title.trim())) {
      return { ok: false, message: "Each stage needs an id and a title." };
    }
    const duplicate = clash(
      filled.map((row) => row.id.trim()),
      "Stage ids must be unique.",
    );
    if (duplicate) return duplicate;
    return {
      ok: true,
      record: {
        stages: filled.map((row) => {
          const stage: Record<string, unknown> = { id: row.id.trim(), title: row.title.trim() };
          const experiment = row.experiment.trim();
          if (experiment) stage.experiment = experiment;
          const dependsOn = splitIds(row.depends);
          if (dependsOn.length > 0) stage.depends_on = dependsOn;
          return stage;
        }),
      },
    };
  }
  if (cls === "Todo") {
    const filled = draft.items.filter(
      (row) => row.id.trim() || row.title.trim() || row.stage.trim(),
    );
    if (filled.length === 0 || filled.some((row) => !row.id.trim() || !row.title.trim())) {
      return { ok: false, message: "Each item needs an id and a title." };
    }
    const duplicate = clash(
      filled.map((row) => row.id.trim()),
      "Todo ids must be unique.",
    );
    if (duplicate) return duplicate;
    return {
      ok: true,
      record: {
        items: filled.map((row) => {
          const item: Record<string, unknown> = {
            id: row.id.trim(),
            title: row.title.trim(),
            status: row.status,
          };
          const stage = row.stage.trim();
          if (stage) item.stage = stage;
          return item;
        }),
      },
    };
  }
  const stage = draft.milestone.stage.trim();
  const criterion = draft.milestone.criterion.trim();
  if (!stage || !criterion) {
    return { ok: false, message: "A milestone needs the stage it closes and a criterion." };
  }
  return {
    ok: true,
    record: { stage, criterion, status: draft.milestone.status },
  };
};

export interface RoadmapStageView {
  id: string;
  title: string;
  experiment?: string;
  dependsOn: string[];
}

export interface TodoItemView {
  id: string;
  title: string;
  status: string;
  stage?: string;
}

export type PlanningView =
  | { kind: "roadmap"; stages: RoadmapStageView[] }
  | { kind: "todo"; items: TodoItemView[] }
  | { kind: "milestone"; stage: string; criterion: string; status: string }
  | { kind: "delegation"; goal: string; scope: string; state: string };

const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

/** Read a note's record for display. A mismatched shape renders nothing. */
export const planningView = (cls: string, record: unknown): PlanningView | null => {
  if (!isObject(record)) return null;
  if (cls === "Roadmap") {
    if (!Array.isArray(record.stages) || record.stages.length === 0) return null;
    const stages: RoadmapStageView[] = [];
    for (const item of record.stages) {
      if (!isObject(item) || typeof item.id !== "string" || typeof item.title !== "string") {
        return null;
      }
      stages.push({
        id: item.id,
        title: item.title,
        experiment:
          typeof item.experiment === "string" && item.experiment ? item.experiment : undefined,
        dependsOn: strings(item.depends_on),
      });
    }
    return { kind: "roadmap", stages };
  }
  if (cls === "Todo") {
    if (!Array.isArray(record.items) || record.items.length === 0) return null;
    const items: TodoItemView[] = [];
    for (const item of record.items) {
      if (!isObject(item) || typeof item.id !== "string" || typeof item.title !== "string") {
        return null;
      }
      items.push({
        id: item.id,
        title: item.title,
        status: typeof item.status === "string" ? item.status : "open",
        stage: typeof item.stage === "string" && item.stage ? item.stage : undefined,
      });
    }
    return { kind: "todo", items };
  }
  if (cls === "Milestone") {
    if (typeof record.stage !== "string" || typeof record.criterion !== "string") return null;
    if (!record.stage || !record.criterion) return null;
    return {
      kind: "milestone",
      stage: record.stage,
      criterion: record.criterion,
      status: typeof record.status === "string" ? record.status : "open",
    };
  }
  if (cls === "Delegation") {
    const goal = typeof record.goal === "string" ? record.goal : "";
    const scope = typeof record.scope === "string" ? record.scope : "";
    if (!goal && !scope) return null;
    return {
      kind: "delegation",
      goal,
      scope,
      state: typeof record.state === "string" ? record.state : "open",
    };
  }
  return null;
};
