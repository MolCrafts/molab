/**
 * How the run components of a knowledge page find what they show: an
 * experiment or a run by its `molab:` ref (through the page's snapshot), the
 * preview target of a run, and the scalar results of an experiment's runs.
 */

import { useMemo } from "react";
import type { PreviewTarget } from "@/app/preview/target";
import { useRunSiblings } from "@/app/renderers/run/useRunSiblings";
import type { ExperimentSummary, RunSummary } from "@/app/types";
import { type DocContextValue, useDoc } from "../context";
import { resolveDocRef } from "../RefChip";

export const runPreviewTarget = (run: RunSummary): PreviewTarget => ({
  kind: "run",
  projectId: run.projectId,
  experimentId: run.experimentId,
  runId: run.id,
  ...(run.workspaceKey ? { workspaceKey: run.workspaceKey } : {}),
});

const findExperiment = (doc: DocContextValue, ref: string): ExperimentSummary | null => {
  const direct = doc.snapshot.experiments.find((item) => item.ref === ref);
  if (direct) return direct;
  const target = resolveDocRef(ref, doc.refIndex, doc.snapshot)?.target;
  if (target?.kind !== "experiment") return null;
  return doc.snapshot.experiments.find((item) => item.id === target.experimentId) ?? null;
};

const findRun = (doc: DocContextValue, ref: string): RunSummary | null => {
  const direct = doc.snapshot.runs.find((item) => item.ref === ref);
  if (direct) return direct;
  const target = resolveDocRef(ref, doc.refIndex, doc.snapshot)?.target;
  if (target?.kind !== "run") return null;
  return doc.snapshot.runs.find((item) => item.id === target.runId) ?? null;
};

export interface DocExperiment {
  experiment: ExperimentSummary;
  runs: readonly RunSummary[];
}

/** The experiment *ref* names and its runs in the snapshot; null when it does not resolve. */
export const useDocExperiment = (ref: string | undefined): DocExperiment | null => {
  const doc = useDoc();
  return useMemo(() => {
    const experiment = ref ? findExperiment(doc, ref) : null;
    if (!experiment) return null;
    const runs = doc.snapshot.runs.filter(
      (run) =>
        run.experimentId === experiment.id &&
        (experiment.workspaceKey === undefined ||
          run.workspaceKey === undefined ||
          run.workspaceKey === experiment.workspaceKey),
    );
    return { experiment, runs };
  }, [doc, ref]);
};

/** The run *ref* names; null when it does not resolve. */
export const useDocRun = (ref: string | undefined): RunSummary | null => {
  const doc = useDoc();
  return useMemo(() => (ref ? findRun(doc, ref) : null), [doc, ref]);
};

export interface RunResults {
  /** Run id → scalar results of its last succeeded attempt (null: none yet). */
  byRun: ReadonlyMap<string, Readonly<Record<string, unknown>> | null>;
  loading: boolean;
}

/**
 * Scalar results of an experiment's runs — the same per-attempt outputs query
 * the experiment Overview's key-result chart reads (`useRunSiblings`).
 */
export const useRunResults = (experimentId: string | null, enabled: boolean): RunResults => {
  const { siblings, loading } = useRunSiblings(experimentId ? { id: "", experimentId } : null, {
    results: enabled,
  });
  const byRun = useMemo(
    () => new Map(siblings.map((sibling) => [sibling.id, sibling.results ?? null] as const)),
    [siblings],
  );
  return { byRun, loading: enabled && loading };
};
