import { planningView } from "./planningModel";

export interface StageTodoCounts {
  done: number;
  open: number;
  blocked: number;
  total: number;
}

export interface StageMilestone {
  name: string;
  path: string;
  status: string;
  criterion: string;
}

export interface StageProgress {
  id: string;
  title: string;
  experiment?: string;
  milestone?: StageMilestone;
  todos: StageTodoCounts;
  /** Met, Missed, Blocked, Done, or Open. */
  word: string;
}

export interface CampaignProgress {
  roadmapTitle: string;
  roadmapPath: string;
  planTitle: string | null;
  planPath: string | null;
  stages: StageProgress[];
}

export interface PlanningNote {
  cls: string;
  name: string;
  relPath: string;
  record: unknown;
}

const emptyTodos = (): StageTodoCounts => ({ done: 0, open: 0, blocked: 0, total: 0 });

const wordFor = (milestone: string | undefined, todos: StageTodoCounts): string => {
  if (milestone === "met") return "Met";
  if (milestone === "missed") return "Missed";
  if (todos.blocked > 0) return "Blocked";
  if (todos.total > 0 && todos.done === todos.total) return "Done";
  return "Open";
};

/**
 * One campaign per roadmap. Milestones and todos attach by stage id.
 * A single Plan in the same set is the campaign name.
 */
export const buildCampaigns = (notes: readonly PlanningNote[]): CampaignProgress[] => {
  const plans = notes.filter((note) => note.cls === "Plan");
  const plan = plans.length === 1 ? plans[0] : null;
  const campaigns: CampaignProgress[] = [];
  for (const note of notes) {
    if (note.cls !== "Roadmap") continue;
    const view = planningView("Roadmap", note.record);
    if (view == null) continue;
    if (view.kind !== "roadmap") continue;
    const stages: StageProgress[] = view.stages.map((stage) => ({
      id: stage.id,
      title: stage.title,
      experiment: stage.experiment,
      todos: emptyTodos(),
      word: "Open",
    }));
    const byId = new Map(stages.map((stage) => [stage.id, stage]));
    for (const other of notes) {
      if (other.cls === "Milestone") {
        const milestone = planningView("Milestone", other.record);
        if (milestone == null) continue;
        if (milestone.kind !== "milestone") continue;
        const stage = byId.get(milestone.stage);
        if (!stage || stage.milestone) continue;
        stage.milestone = {
          name: other.name,
          path: other.relPath,
          status: milestone.status,
          criterion: milestone.criterion,
        };
      } else if (other.cls === "Todo") {
        const todo = planningView("Todo", other.record);
        if (todo == null) continue;
        if (todo.kind !== "todo") continue;
        for (const item of todo.items) {
          const stage = item.stage ? byId.get(item.stage) : undefined;
          if (!stage) continue;
          stage.todos.total += 1;
          if (item.status === "done") stage.todos.done += 1;
          else if (item.status === "blocked") stage.todos.blocked += 1;
          else stage.todos.open += 1;
        }
      }
    }
    for (const stage of stages) {
      stage.word = wordFor(stage.milestone?.status, stage.todos);
    }
    campaigns.push({
      roadmapTitle: note.name,
      roadmapPath: note.relPath,
      planTitle: plan?.name ?? null,
      planPath: plan?.relPath ?? null,
      stages,
    });
  }
  return campaigns;
};
