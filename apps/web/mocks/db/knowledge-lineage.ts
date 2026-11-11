/** Synthetic, internally connected research history for the Knowledge canvas. */
import type { EmbedRole } from "@/api/knowledge";

const project = "projects/nve-drift";
const benchmark = `${project}/experiments/integrator-benchmark`;
const thermostat = `${project}/experiments/thermostat-validation`;
export const lineagePaths = {
  plan: `${thermostat}/knowledges/thermostat-validation.md`,
  observation: `${project}/knowledges/temperature-stability.md`,
  finding: `${benchmark}/knowledges/integrator-energy-conservation.md`,
  literature: `${project}/knowledges/integrator-reference.md`,
  hypothesis: `${benchmark}/knowledges/timestep-hypothesis.md`,
  counterexample: `${benchmark}/knowledges/coarse-timestep-drift.md`,
  oldDecision: `${project}/knowledges/initial-timestep-policy.md`,
  decision: `${project}/knowledges/revised-timestep-policy.md`,
  report: `${project}/knowledges/timestep-review.md`,
  roadmap: `${thermostat}/knowledges/thermostat-roadmap.md`,
  todo: `${thermostat}/knowledges/thermostat-todo.md`,
  milestone: `${thermostat}/knowledges/relaxation-times-compared.md`,
};
export const lineageNotes = [
  {
    cls: "Literature",
    name: "Integrator reference",
    relPath: lineagePaths.literature,
    hostPath: project,
    excerpt: "Illustrative reference for timestep selection; not a published scientific result.",
    record: {},
  },
  {
    cls: "Hypothesis",
    name: "Timestep hypothesis",
    relPath: lineagePaths.hypothesis,
    hostPath: benchmark,
    excerpt:
      "A 2 fs timestep preserves the same energy drift as 0.5 fs. Synthetic claim, refuted by the coarse-step example.",
    record: { verdict: "refuted" },
  },
  {
    cls: "Finding",
    name: "Coarse timestep drift",
    relPath: lineagePaths.counterexample,
    hostPath: benchmark,
    excerpt:
      "Illustrative counterexample: the 2 fs trace drifts above the demonstration threshold.",
    record: {},
  },
  {
    cls: "Decision",
    name: "Initial timestep policy",
    relPath: lineagePaths.oldDecision,
    hostPath: project,
    excerpt: "Initial example policy: use 2 fs pending validation. Kept for revision history.",
    record: { status: "made" },
  },
  {
    cls: "Decision",
    name: "Revised timestep policy",
    relPath: lineagePaths.decision,
    hostPath: project,
    excerpt:
      "Use 0.5 fs in the example benchmark; replaces the initial policy after reviewing both findings.",
    record: { status: "made" },
  },
  {
    cls: "Report",
    name: "Timestep review",
    relPath: lineagePaths.report,
    hostPath: project,
    excerpt:
      "Synthetic review tracing the plan, observation, conflicting evidence and policy revision.",
    record: {},
  },
];
export const lineageLinks: Record<string, { target: string; role: EmbedRole; label: string }[]> = {
  [lineagePaths.plan]: [
    { target: lineagePaths.literature, role: "cites", label: "Integrator reference" },
  ],
  [lineagePaths.literature]: [
    {
      target: "https://example.org/synthetic-integrator-reference",
      role: "cites",
      label: "Illustrative external reference",
    },
  ],
  [lineagePaths.hypothesis]: [
    { target: lineagePaths.plan, role: "derived_from", label: "Research question" },
  ],
  [lineagePaths.observation]: [
    { target: lineagePaths.plan, role: "derived_from", label: "Validation plan" },
    { target: "molab:experiment/exp-nve/run/md-001", role: "records", label: "Example NVE run" },
  ],
  [lineagePaths.finding]: [
    { target: lineagePaths.observation, role: "derived_from", label: "Temperature observation" },
    { target: lineagePaths.hypothesis, role: "supports", label: "Low-step evidence" },
    {
      target: "molab:asset/asset-nve-trajectory",
      role: "derived_from",
      label: "Example trajectory",
    },
  ],
  [lineagePaths.counterexample]: [
    { target: lineagePaths.observation, role: "derived_from", label: "Temperature observation" },
    { target: lineagePaths.hypothesis, role: "contradicts", label: "Coarse-step counterexample" },
  ],
  [lineagePaths.oldDecision]: [
    { target: lineagePaths.hypothesis, role: "derived_from", label: "Initial assumption" },
  ],
  [lineagePaths.decision]: [
    { target: lineagePaths.finding, role: "derived_from", label: "Low-step finding" },
    { target: lineagePaths.counterexample, role: "derived_from", label: "Coarse-step finding" },
    { target: lineagePaths.oldDecision, role: "supersedes", label: "Initial timestep policy" },
  ],
  [lineagePaths.report]: [
    { target: lineagePaths.decision, role: "derived_from", label: "Revised policy" },
    { target: lineagePaths.literature, role: "cites", label: "Integrator reference" },
    {
      target: "knowledges/molecular-simulation-methods.md",
      role: "references",
      label: "Workspace background",
    },
    {
      target: `${project}/knowledges/unavailable-calibration.md`,
      role: "references",
      label: "Missing calibration note",
    },
  ],
  [lineagePaths.roadmap]: [
    { target: lineagePaths.plan, role: "derived_from", label: "Validation plan" },
  ],
  [lineagePaths.todo]: [{ target: lineagePaths.roadmap, role: "derived_from", label: "Roadmap" }],
  [lineagePaths.milestone]: [
    { target: lineagePaths.report, role: "derived_from", label: "Review evidence" },
  ],
};
