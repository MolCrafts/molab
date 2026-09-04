import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp } from "lucide-react";
import { useMemo } from "react";
import { useInspectedTask } from "@/app/state/inspectedTask";
import type { ScopedRendererProps, TaskSelection } from "@/app/types";
import { Code as InlineCode } from "@/components/ui/code";
import { WorkbenchIconAction, WorkbenchTag } from "@/components/workbench";

/**
 * TaskViewer — the right-inspector panel shown when a workflow-graph node is
 * clicked. It renders *in place* over the current run page (the graph stays in
 * the center); it is never a standalone navigable page. Shows the task's
 * identity, its place in the DAG (upstream → this → downstream, each clickable
 * to re-pin the inspector), and the run assets it produced.
 */
const formatConfigValue = (value: unknown): string => {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};

const Section = ({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): JSX.Element => (
  <div className="px-3 py-3">
    <h3 className="mb-2 text-micro font-medium uppercase tracking-wide text-muted-foreground">
      {title}
    </h3>
    {children}
  </div>
);

export const TaskViewer = ({
  selection,
  snapshot,
}: ScopedRendererProps<"runs" | "workflows" | "experiments">): JSX.Element | null => {
  const { inspectTask, clearInspectedTask } = useInspectedTask();

  const task = selection.objectType === "task" ? (selection as TaskSelection) : null;
  const runId = task?.runId ?? "";
  const taskId = task?.taskId ?? "";

  const run = useMemo(() => snapshot.runs.find((r) => r.id === runId), [snapshot.runs, runId]);
  const workflow = useMemo(() => {
    // From a run page, scope to the run's experiment; in a compiled preview
    // (no run) resolve the owning workflow by which graph contains the node.
    if (run) return snapshot.workflows.find((w) => w.experimentId === run.experimentId) ?? null;
    return (
      snapshot.workflows.find((w) => w.graph?.task_configs.some((n) => n.id === taskId)) ?? null
    );
  }, [snapshot.workflows, run, taskId]);
  const node = workflow?.graph?.task_configs.find((n) => n.id === taskId) ?? null;
  const links = workflow?.graph?.links ?? [];
  const upstream = links.filter((e) => e.to === taskId).map((e) => e.from);
  const downstream = links.filter((e) => e.from === taskId).map((e) => e.to);

  if (!task) return null;

  const TaskChips = ({ ids }: { ids: string[] }): JSX.Element =>
    ids.length === 0 ? (
      <span className="text-label text-muted-foreground">none</span>
    ) : (
      <div className="min-w-0 divide-y divide-border/60">
        {ids.map((id) => (
          <div key={id} className="flex min-w-0 items-center gap-2 py-1">
            <span className="min-w-0 flex-1 truncate font-mono text-label text-foreground">
              {id}
            </span>
            <WorkbenchIconAction
              label={`Inspect task ${id}`}
              onClick={() => inspectTask(id, runId)}
            >
              <ArrowRight className="size-3.5" />
            </WorkbenchIconAction>
          </div>
        ))}
      </div>
    );

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex items-center justify-between gap-2 border-b border-border/70 bg-muted/20 px-3 py-2">
        <h2 className="truncate text-micro font-medium uppercase tracking-wide text-muted-foreground">
          Task
        </h2>
        {node?.type && (
          <WorkbenchTag className="h-5 px-2 text-micro uppercase tracking-wide">
            {node.type}
          </WorkbenchTag>
        )}
      </div>

      <div className="flex-1 divide-y divide-border/50 overflow-auto">
        <Section title="Identity">
          <p className="truncate font-mono text-body-lg font-semibold text-foreground">{taskId}</p>
          <p className="mt-1 font-mono text-micro text-muted-foreground">
            [{node?.label ?? node?.type ?? "—"}]
          </p>
          {run && (
            <div className="mt-1 flex items-center gap-1 text-label text-muted-foreground">
              <WorkbenchIconAction
                label={`Back to ${run.name ?? run.id}`}
                onClick={clearInspectedTask}
              >
                <ArrowLeft className="size-3.5" />
              </WorkbenchIconAction>
              <span className="truncate">{run.name ?? run.id}</span>
            </div>
          )}
        </Section>

        {node?.source ? (
          <Section title="Source">
            <pre className="max-h-80 overflow-auto rounded-control border border-border/60 bg-muted/30 p-3 font-mono text-micro leading-relaxed text-foreground">
              <InlineCode>{node.source}</InlineCode>
            </pre>
          </Section>
        ) : (
          <Section title="Source">
            <p className="text-label italic text-muted-foreground">
              No source captured for this node.
            </p>
          </Section>
        )}

        {node?.config && Object.keys(node.config).length > 0 && (
          <Section title="Inputs">
            <dl className="space-y-1">
              {Object.entries(node.config).map(([key, value]) => (
                <div key={key} className="flex gap-2 text-label">
                  <dt className="flex-none font-medium text-muted-foreground">{key}</dt>
                  <dd className="min-w-0 flex-1 break-all text-right font-mono text-foreground">
                    {formatConfigValue(value)}
                  </dd>
                </div>
              ))}
            </dl>
          </Section>
        )}

        <Section title="Upstream">
          <div className="flex items-center gap-2">
            <ArrowUp className="h-3 w-3 flex-none text-muted-foreground" />
            <TaskChips ids={upstream} />
          </div>
        </Section>

        <Section title="Downstream">
          <div className="flex items-center gap-2">
            <ArrowDown className="h-3 w-3 flex-none text-muted-foreground" />
            <TaskChips ids={downstream} />
          </div>
        </Section>

      </div>
    </div>
  );
};
