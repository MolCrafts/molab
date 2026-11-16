/**
 * Experiment and project Previews (Figma L12-3, L12-4): the container's one
 * line (the worst state, never a repeated status word), its runs as one Vega
 * status bar with a key, and the latest runs — each re-targets the Preview.
 * Runs come from the run inventory, not the snapshot: the snapshot loads an
 * experiment's runs only once it is opened, so it would call a busy experiment empty.
 */

import { useMemo } from "react";
import { StatusBar } from "@/app/components/entity/gauges/vega/charts";
import { StatusIcon } from "@/app/components/entity/StatusIcon";
import { useScopeRuns } from "@/app/dashboard/useScopeRuns";
import { entityMeta } from "@/app/entities/kinds";
import { experimentPath } from "@/app/entities/paths";
import { runLabel } from "@/app/runs/runTitle";
import type { WorkspaceRunRow } from "@/app/runs/types";
import {
  countStatuses,
  isActiveStatus,
  latestStatus,
  needsAttention,
  type StatusKey,
} from "@/app/status/vocabulary";
import type { WorkspaceSnapshot } from "@/app/types";
import { WorkbenchAction } from "@/components/workbench";
import { KindIcon, PreviewFrame, PreviewLink, PreviewSubhead } from "./PreviewFrame";
import { PreviewGone } from "./PreviewStates";
import { PreviewRow, PreviewVerdict, StatusWords } from "./previewParts";
import type { PreviewTarget } from "./target";

type ContainerTarget = Extract<PreviewTarget, { kind: "experiment" | "project" }>;

interface ContainerPreviewProps {
  target: ContainerTarget;
  snapshot: WorkspaceSnapshot;
  onPreview: (target: PreviewTarget) => void;
  onOpen: (target: PreviewTarget, path?: string) => void;
  onOpenInBackground: () => void;
  onClose: () => void;
}

/** A run as the Preview lists it: its latest status and when that attempt began. */
interface PreviewRun {
  id: string;
  projectId: string;
  experimentId: string;
  label: string;
  status: StatusKey;
  at: string;
}

const previewRunOf = (row: WorkspaceRunRow): PreviewRun => {
  const latest = row.executions.at(-1);
  return {
    id: row.id,
    projectId: row.projectId,
    experimentId: row.experimentId,
    label: runLabel(row),
    status: latestStatus(row.executions),
    at: latest?.startedAt ?? latest?.createdAt ?? "",
  };
};

const runNeedsAttention = (run: PreviewRun): boolean => needsAttention(run.status);
const isActive = (run: PreviewRun): boolean => isActiveStatus(run.status);
const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? "" : "s"}`;

export const ContainerPreview = ({
  target,
  snapshot,
  onPreview,
  onOpen,
  onOpenInBackground,
  onClose,
}: ContainerPreviewProps): JSX.Element => {
  const project = snapshot.projects.find((item) => item.id === target.projectId) ?? null;
  const experiment =
    target.kind === "experiment"
      ? (snapshot.experiments.find((item) => item.id === target.experimentId) ?? null)
      : null;
  const { rows } = useScopeRuns(
    target.kind === "experiment"
      ? { experimentId: target.experimentId }
      : { projectId: target.projectId },
    true,
  );
  const runs = useMemo(() => rows.map(previewRunOf), [rows]);
  const counts = useMemo(() => countStatuses(runs.map((run) => run.status)), [runs]);
  const subject = target.kind === "experiment" ? experiment : project;
  const title =
    subject?.name ?? (target.kind === "experiment" ? target.experimentId : target.projectId);
  const frame = { title, onOpen: () => onOpen(target), onOpenInBackground, onClose };
  if (!subject) return <PreviewGone {...frame} kindLabel={target.kind} />;

  const attention = runs.filter(runNeedsAttention);
  const active = runs.filter(isActive);
  const experiments = snapshot.experiments.filter((item) => item.projectId === target.projectId);
  const loaded = runs.length > 0;
  const line =
    target.kind === "experiment"
      ? !loaded
        ? "No runs yet"
        : attention.length > 0
          ? `${attention.length} of ${plural(runs.length, "run")} need attention`
          : `${plural(runs.length, "run")}`
      : (() => {
          const flagged = experiments.filter((item) =>
            runs.some((run) => run.experimentId === item.id && runNeedsAttention(run)),
          );
          return flagged.length > 0
            ? `${flagged.length} of ${plural(experiments.length, "experiment")} need attention`
            : plural(experiments.length, "experiment");
        })();
  const worst =
    attention.length > 0 ? "failed" : active.length > 0 ? "running" : loaded ? "succeeded" : "none";
  const latest = [...runs].sort((left, right) => right.at.localeCompare(left.at)).slice(0, 3);
  const context =
    target.kind === "experiment"
      ? ["experiment", project?.name, loaded ? plural(runs.length, "run") : null]
          .filter(Boolean)
          .join(" · ")
      : [
          "project",
          plural(experiments.length, "experiment"),
          loaded ? plural(runs.length, "run") : null,
        ]
          .filter(Boolean)
          .join(" · ");

  return (
    <PreviewFrame
      {...frame}
      lead={<KindIcon icon={entityMeta(target.kind).icon} />}
      context={context}
      announcement={`${title}. ${line}`}
      copies={[
        {
          label: `${target.kind === "experiment" ? "Experiment" : "Project"} id`,
          value: target.kind === "experiment" ? target.experimentId : target.projectId,
        },
      ]}
      actions={
        target.kind === "experiment" ? (
          <WorkbenchAction
            kind="primary"
            size="content"
            className="h-shell-button rounded-hairline bg-accent px-3 font-normal text-accent-foreground hover:bg-accent-hover"
            onClick={() =>
              onOpen(
                target,
                `${experimentPath(target.projectId, target.experimentId, "runs")}?run=new`,
              )
            }
          >
            New run
          </WorkbenchAction>
        ) : undefined
      }
    >
      <PreviewVerdict
        status={worst}
        subject={line}
        right={active.length > 0 ? `${active.length} active` : undefined}
      />
      {loaded ? (
        <>
          <div className="pl-6">
            <StatusBar
              group={{ id: target.kind, label: title, counts }}
              label={`Runs of ${title} by state`}
            />
          </div>
          <StatusWords counts={counts} />
          <PreviewSubhead>Latest</PreviewSubhead>
          <ul className="pl-6 text-body">
            {latest.map((run) => (
              <PreviewRow key={run.id} status={run.status}>
                <PreviewLink
                  onClick={() =>
                    onPreview({
                      kind: "run",
                      runId: run.id,
                      projectId: run.projectId,
                      experimentId: run.experimentId,
                    })
                  }
                >
                  {run.label}
                </PreviewLink>
              </PreviewRow>
            ))}
          </ul>
        </>
      ) : null}
      {target.kind === "project" ? (
        <ul className="pl-6 text-body">
          {experiments.map((item) => (
            <PreviewRow
              key={item.id}
              status={
                runs.some((run) => run.experimentId === item.id && runNeedsAttention(run))
                  ? "failed"
                  : undefined
              }
            >
              <PreviewLink
                mono={false}
                onClick={() =>
                  onPreview({
                    kind: "experiment",
                    projectId: item.projectId,
                    experimentId: item.id,
                  })
                }
              >
                {item.name}
              </PreviewLink>
            </PreviewRow>
          ))}
        </ul>
      ) : null}
      {!loaded && target.kind === "experiment" ? (
        <p className="flex items-center gap-2 pl-6 text-label text-muted-foreground">
          <StatusIcon status="pending" className="size-icon-sm" />
          Nothing has run in this experiment.
        </p>
      ) : null}
    </PreviewFrame>
  );
};
