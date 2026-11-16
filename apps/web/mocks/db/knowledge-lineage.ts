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
  oldPolicy: `${project}/knowledges/initial-timestep-policy.md`,
  policy: `${project}/knowledges/revised-timestep-policy.md`,
  report: `${project}/knowledges/timestep-review.md`,
};
export const lineageNotes = [
  {
    cls: "Literature",
    name: "Integrator reference",
    relPath: lineagePaths.literature,
    hostPath: project,
    excerpt: "Illustrative reference for timestep selection; not a published scientific result.",
    fields: {},
  },
  {
    cls: "Hypothesis",
    name: "Timestep hypothesis",
    relPath: lineagePaths.hypothesis,
    hostPath: benchmark,
    excerpt:
      "A 2 fs timestep preserves the same energy drift as 0.5 fs. Synthetic claim, refuted by the coarse-step example.",
    fields: { verdict: "refuted" },
  },
  {
    cls: "Finding",
    name: "Coarse timestep drift",
    relPath: lineagePaths.counterexample,
    hostPath: benchmark,
    excerpt:
      "Illustrative counterexample: the 2 fs trace drifts above the demonstration threshold.",
    fields: {},
  },
  {
    cls: "Plan",
    name: "Initial timestep policy",
    relPath: lineagePaths.oldPolicy,
    hostPath: project,
    excerpt: "Initial example policy: use 2 fs pending validation. Kept for revision history.",
    fields: {},
  },
  {
    cls: "Plan",
    name: "Revised timestep policy",
    relPath: lineagePaths.policy,
    hostPath: project,
    excerpt:
      "Use 0.5 fs in the example benchmark; replaces the initial policy after reviewing both findings.",
    fields: {},
  },
  {
    cls: "Report",
    name: "Timestep review",
    relPath: lineagePaths.report,
    hostPath: project,
    excerpt:
      "Synthetic review tracing the plan, observation, conflicting evidence and policy revision.",
    fields: {},
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
    {
      target: "molab:experiment/exp-nve/run/md-001",
      role: "derived_from",
      label: "Example NVE run",
    },
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
  [lineagePaths.oldPolicy]: [
    { target: lineagePaths.hypothesis, role: "derived_from", label: "Initial assumption" },
  ],
  [lineagePaths.policy]: [
    { target: lineagePaths.finding, role: "derived_from", label: "Low-step finding" },
    { target: lineagePaths.counterexample, role: "derived_from", label: "Coarse-step finding" },
    { target: lineagePaths.oldPolicy, role: "derived_from", label: "Initial timestep policy" },
  ],
  [lineagePaths.report]: [
    { target: lineagePaths.policy, role: "derived_from", label: "Revised policy" },
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
};
