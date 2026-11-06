import type { JSX } from "react";
import { type PlanningView, planningView } from "./planningModel";

const heading = "text-label font-semibold uppercase tracking-wide text-muted-foreground";
const meta = "text-label text-muted-foreground";

const RoadmapStages = ({ view }: { view: Extract<PlanningView, { kind: "roadmap" }> }) => (
  <section aria-label="Stages" className="space-y-3 border-b border-border/50 pb-4">
    <h3 className={heading}>Stages</h3>
    <ol className="space-y-3">
      {view.stages.map((stage, index) => (
        <li key={stage.id} className="grid grid-cols-[1.5rem_1fr] gap-x-2">
          <span className="font-mono text-micro text-muted-foreground">{index + 1}</span>
          <span className="min-w-0">
            <span className="text-body-lg font-medium text-foreground">{stage.title}</span>
            <span className="ml-2 font-mono text-micro text-muted-foreground">{stage.id}</span>
            {(stage.experiment || stage.dependsOn.length > 0) && (
              <span className={`mt-1 block ${meta}`}>
                {[
                  stage.experiment ? `Experiment ${stage.experiment}` : "",
                  stage.dependsOn.length > 0 ? `Depends on ${stage.dependsOn.join(", ")}` : "",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            )}
          </span>
        </li>
      ))}
    </ol>
  </section>
);

const TodoItems = ({ view }: { view: Extract<PlanningView, { kind: "todo" }> }) => (
  <section aria-label="Items" className="space-y-3 border-b border-border/50 pb-4">
    <h3 className={heading}>Items</h3>
    <ul className="space-y-3">
      {view.items.map((item) => (
        <li key={item.id} className="min-w-0">
          <span className="text-micro uppercase tracking-wide text-muted-foreground">
            {item.status}
          </span>
          <span className="mt-1 block text-body-lg font-medium text-foreground">{item.title}</span>
          <span className={`block font-mono text-micro ${meta}`}>
            {item.id}
            {item.stage ? ` · stage ${item.stage}` : ""}
          </span>
        </li>
      ))}
    </ul>
  </section>
);

const MilestoneCheckpoint = ({ view }: { view: Extract<PlanningView, { kind: "milestone" }> }) => (
  <section aria-label="Checkpoint" className="space-y-3 border-b border-border/50 pb-4">
    <h3 className={heading}>Checkpoint</h3>
    <dl className="grid gap-3 sm:grid-cols-[8rem_1fr]">
      <dt className={meta}>Stage</dt>
      <dd className="font-mono text-body-lg text-foreground">{view.stage}</dd>
      <dt className={meta}>Criterion</dt>
      <dd className="whitespace-pre-wrap text-body-lg text-foreground">{view.criterion}</dd>
      <dt className={meta}>Status</dt>
      <dd className="text-micro uppercase tracking-wide text-foreground">{view.status}</dd>
    </dl>
  </section>
);

const DelegationSummary = ({ view }: { view: Extract<PlanningView, { kind: "delegation" }> }) => (
  <section aria-label="Delegation" className="space-y-3 border-b border-border/50 pb-4">
    <h3 className={heading}>Delegation</h3>
    <dl className="grid gap-3 sm:grid-cols-[8rem_1fr]">
      <dt className={meta}>Goal</dt>
      <dd className="whitespace-pre-wrap text-body-lg text-foreground">{view.goal}</dd>
      <dt className={meta}>Scope</dt>
      <dd className="whitespace-pre-wrap text-body-lg text-foreground">{view.scope}</dd>
      <dt className={meta}>State</dt>
      <dd className="text-micro uppercase tracking-wide text-foreground">{view.state}</dd>
    </dl>
  </section>
);

/** Role fields above the narrative. An empty or mismatched record renders nothing. */
export const PlanningRecord = ({
  cls,
  record,
}: {
  cls: string;
  record: unknown;
}): JSX.Element | null => {
  const view = planningView(cls, record);
  if (!view) return null;
  if (view.kind === "roadmap") return <RoadmapStages view={view} />;
  if (view.kind === "todo") return <TodoItems view={view} />;
  if (view.kind === "milestone") return <MilestoneCheckpoint view={view} />;
  return <DelegationSummary view={view} />;
};
