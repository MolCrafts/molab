/**
 * Params view (Figma L04-6): the run's parameter values with their units,
 * whether each is swept or fixed for the experiment, and how it compares with
 * the baseline — the nearest sibling, named once at the top. Then the inputs
 * it opens and its identity (run id, definition hash, workflow).
 */

import { type JSX, type ReactNode, useMemo } from "react";
import { CopyButton, OverviewCanvas } from "@/app/components/entity";
import {
  baselineOf,
  type ComparedRun,
  type ParameterRow,
  parameterRows,
} from "@/app/renderers/run/runCompare";
import { useRunSiblings } from "@/app/renderers/run/useRunSiblings";
import { runLabel } from "@/app/runs/runTitle";
import type { AssetSummary, RunSummary } from "@/app/types";
import { cn } from "@/lib/utils";

const Table = ({
  title,
  readout,
  children,
}: {
  title: string;
  readout?: ReactNode;
  children: ReactNode;
}): JSX.Element => (
  <section aria-label={title} className="max-w-[45rem]">
    <header className="flex items-baseline gap-3 border-b border-border pb-1">
      <h2 className="text-body text-foreground">{title}</h2>
      {readout ? <span className="ml-auto text-label text-muted-foreground">{readout}</span> : null}
    </header>
    <dl className="divide-y divide-border border-b border-border">{children}</dl>
  </section>
);

const Row = ({
  name,
  value,
  note,
  valueClassName,
  copy,
}: {
  name: string;
  value: ReactNode;
  note?: ReactNode;
  valueClassName?: string;
  copy?: string;
}): JSX.Element => (
  <div className="group grid h-list-row grid-cols-[13rem_11rem_minmax(0,1fr)] items-center gap-x-4 px-list-pad-x">
    <dt className="truncate font-mono text-label text-foreground">{name}</dt>
    <dd className={cn("flex min-w-0 items-center gap-1 font-mono text-label", valueClassName)}>
      <span className="min-w-0 truncate" title={typeof value === "string" ? value : undefined}>
        {value}
      </span>
      {copy ? (
        <CopyButton
          value={copy}
          label={name}
          className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
        />
      ) : null}
    </dd>
    <dd className="truncate text-label text-muted-foreground">{note}</dd>
  </div>
);

const roleNote = (row: ParameterRow): string =>
  row.role === "fixed"
    ? "fixed for the experiment"
    : row.differs === null
      ? "swept"
      : row.differs
        ? "swept · differs from the baseline"
        : "swept · same as the baseline";

const shortHash = (hash: string): string => {
  const [scheme, digest] = hash.includes(":") ? hash.split(":", 2) : ["", hash];
  const body = digest ?? "";
  const short = body.length > 12 ? `${body.slice(0, 4)}…${body.slice(-4)}` : body;
  return scheme ? `${scheme}:${short}` : short;
};

export const RunParams = ({
  run,
  assets,
  workflowLabel,
  onPreviewRun,
  onPreviewAsset,
}: {
  run: RunSummary;
  assets: readonly AssetSummary[];
  /** The experiment's workflow (a document name or a code locator). */
  workflowLabel: string | null;
  onPreviewRun?: (runId: string) => void;
  onPreviewAsset?: (assetId: string) => void;
}): JSX.Element => {
  const { siblings } = useRunSiblings(run);
  const { rows, baseline } = useMemo(() => {
    const self: ComparedRun = {
      id: run.id,
      title: runLabel(run),
      parameters: run.parameters ?? {},
      status: run.status,
    };
    const others = siblings.filter((sibling) => sibling.id !== run.id);
    const nearest = baselineOf(self, others);
    return { rows: parameterRows(self, others, nearest), baseline: nearest };
  }, [run, siblings]);
  const inputs = run.inputs ?? [];

  return (
    <OverviewCanvas>
      <Table
        title="Parameters"
        readout={
          baseline ? (
            <span className="flex items-center gap-1">
              baseline
              <button
                type="button"
                onClick={() => onPreviewRun?.(baseline.id)}
                className="font-mono text-accent hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {baseline.title}
              </button>
            </span>
          ) : null
        }
      >
        {rows.length === 0 ? (
          <p className="px-2 py-1 text-label text-muted-foreground">No parameters</p>
        ) : (
          rows.map((row) => (
            <Row
              key={row.key}
              name={row.key}
              value={row.value}
              note={roleNote(row)}
              valueClassName={
                row.differs ? "font-medium text-diff-modified-foreground" : "text-foreground"
              }
            />
          ))
        )}
      </Table>

      {inputs.length > 0 ? (
        <Table title="Inputs">
          {inputs.map((assetId) => {
            const asset = assets.find((candidate) => candidate.id === assetId);
            return (
              <Row
                key={assetId}
                name={asset?.kind ?? "asset"}
                value={
                  <button
                    type="button"
                    onClick={() => onPreviewAsset?.(assetId)}
                    className="truncate text-accent hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    {asset?.name ?? assetId}
                  </button>
                }
                note={["asset", asset?.scopeKind].filter(Boolean).join(" · ")}
              />
            );
          })}
        </Table>
      ) : null}

      <Table title="Identity">
        <Row name="run id" value={run.id} copy={run.id} valueClassName="text-foreground" />
        {run.definitionHash ? (
          <Row
            name="definition"
            value={shortHash(run.definitionHash)}
            copy={run.definitionHash}
            valueClassName="text-foreground"
          />
        ) : null}
        {workflowLabel ? (
          <Row
            name="workflow"
            value={
              run.experimentRevisionId
                ? `${workflowLabel} · ${shortHash(run.experimentRevisionId)}`
                : workflowLabel
            }
            valueClassName="text-foreground"
          />
        ) : null}
        <Row name="path" value={run.path} copy={run.path} valueClassName="text-muted-foreground" />
      </Table>
    </OverviewCanvas>
  );
};
