// ─────────────────────────────────────────────────────────────────────────────
// What a container's Overview says, derived without React: the experiment
// verdict one level up — the worst latest status across every run of a project
// (L02, grouped by experiment) or of the workspace (L01, grouped by project) —
// with evidence that names the group(s) the runs needing attention sit in, and
// the outcome of each group's runs.
// ─────────────────────────────────────────────────────────────────────────────

import {
  type ExperimentVerdict,
  experimentVerdict,
  firstLine,
  type OutcomeGroup,
  quantifier,
  type StoryRun,
  sharedValues,
} from "@/app/renderers/experiment/experimentStory";
import { runPresentationStatus } from "@/app/runs/projections";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { countStatuses } from "@/app/status/vocabulary";

/** A run of the scope, with the child it belongs to (its experiment, or its project). */
export interface ScopeRun extends StoryRun {
  groupId: string;
}

export interface NamedGroup {
  id: string;
  name: string;
}

/** What the scope's children are called: experiments of a project, projects of a workspace. */
export type GroupNoun = readonly [string, string];
export const EXPERIMENTS: GroupNoun = ["experiment", "experiments"];
export const PROJECTS: GroupNoun = ["project", "projects"];

/**
 * One group: "Both in Integrator Benchmark, at timestep_fs = 2 fs · <errors>".
 * Several: "In 3 projects · NVE Drift 2 · Protein Folding 1 · <errors>".
 */
const attentionEvidence = (
  runs: readonly ScopeRun[],
  attention: readonly ScopeRun[],
  groups: readonly NamedGroup[],
  noun: GroupNoun,
): string | null => {
  if (attention.length === 0) return null;
  const nameOf = (id: string): string => groups.find((group) => group.id === id)?.name ?? id;
  const counts = new Map<string, number>();
  for (const run of attention) counts.set(run.groupId, (counts.get(run.groupId) ?? 0) + 1);
  const errors = [
    ...new Set(attention.map((run) => firstLine(run.errorMessage)).filter(Boolean)),
  ].slice(0, 2) as string[];
  if (counts.size > 1) {
    const each = [...counts.entries()]
      .sort((left, right) => right[1] - left[1])
      .map(([id, count]) => `${nameOf(id)} ${count}`);
    return [`In ${counts.size} ${noun[1]}`, ...each, ...errors].join(" · ");
  }
  const [only] = [...counts.keys()];
  const name = nameOf(only ?? "");
  const lead = attention.length === 1 ? `In ${name}` : `${quantifier(attention.length)} in ${name}`;
  // Shared values only mean something among one group's runs.
  const shared = sharedValues(
    attention,
    runs.filter((run) => run.groupId === only),
  );
  return [shared.length > 0 ? `${lead}, at ${shared.join(", ")}` : lead, ...errors].join(" · ");
};

/** The scope's verdict: an experiment verdict over all its runs, located by group. */
export const scopeVerdict = (
  runs: readonly ScopeRun[],
  groups: readonly NamedGroup[],
  noun: GroupNoun = EXPERIMENTS,
): ExperimentVerdict => {
  if (groups.length === 0 && runs.length === 0) {
    return {
      state: "empty",
      status: "pending",
      word: "Empty",
      subject: `No ${noun[1]} yet`,
      aside: null,
      evidence: null,
      subjectFilter: null,
      asideFilter: null,
      attention: [],
    };
  }
  const verdict = experimentVerdict(runs);
  if (verdict.state !== "attention") return verdict;
  const attention = runs.filter((run) => verdict.attention.includes(run.id));
  return { ...verdict, evidence: attentionEvidence(runs, attention, groups, noun) };
};

/** The latest status of each run, by group, in the groups' order; groups with no run are left out. */
export const outcomeByGroup = (
  runs: readonly ScopeRun[],
  groups: readonly NamedGroup[],
): OutcomeGroup[] =>
  groups
    .map((group) => ({
      id: group.id,
      label: group.name,
      counts: countStatuses(
        runs.filter((run) => run.groupId === group.id).map((run) => run.status),
      ),
    }))
    .filter((group) => group.counts.total > 0);

/**
 * A verdict filter (`status:failed,interrupted`) as the workspace Runs URL,
 * scoped to a project when one is given. Any other filter opens the runs unfiltered.
 */
export const runsHref = (filter?: string, projectId?: string): string => {
  const params = new URLSearchParams(projectId ? { projectId } : {});
  const match = filter?.match(/^status:(.+)$/);
  if (match?.[1]) params.set("status", match[1]);
  const query = params.toString();
  return query ? `/runs?${query}` : "/runs";
};

/**
 * The scope's runs for the story, from the run inventory (each run's latest
 * status), grouped by experiment or by project; the first error line comes
 * from the snapshot when it has the run.
 */
export const scopeRunsOf = (
  rows: readonly WorkspaceRunRow[],
  known: readonly { id: string; errorMessage?: string | null }[],
  by: "experiment" | "project",
): ScopeRun[] =>
  rows.map((row) => ({
    id: row.id,
    status: runPresentationStatus(row),
    groupId: by === "experiment" ? row.experimentId : row.projectId,
    parameters: row.parameters,
    errorMessage: known.find((run) => run.id === row.id)?.errorMessage ?? null,
  }));
