/**
 * `<molab-log run=… attempt=e01 file=run.log lines=1182-1185>` (L10): an
 * excerpt of one attempt's log, its lines numbered, error lines marked. ↗
 * opens the run's Logs view at the first line. Logs are read through the
 * attempt log API (`run.log` / `stdout.log` / `stderr.log`); any other
 * attempt-relative file through the attempt's file-text API — the browser
 * never composes a workspace path.
 */

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, ScrollText, Terminal } from "lucide-react";
import type { JSX } from "react";
import { runPath } from "@/app/entities/paths";
import { usePreview } from "@/app/preview/PreviewContext";
import { runLabel } from "@/app/runs/runTitle";
import { journalRefetchInterval, runFileTextQueryOptions } from "@/app/state/entityQueries";
import { executionLogQueryOptions } from "@/app/state/executionLog";
import type { RunSummary } from "@/app/types";
import { cn } from "@/lib/utils";
import type { DocComponentProps, DocComponentSpec } from "../context";
import { ComponentFrame, ComponentLoading, ComponentNotice } from "../frame";
import { runPreviewTarget, useDocRun } from "./docRuns";
import {
  type ExcerptLine,
  excerptLines,
  type LineRange,
  parseLineRange,
  streamOfFile,
} from "./logExcerpt";

const NAME = "molab-log";
const DEFAULT_FILE = "run.log";

interface LogSource {
  text: string | null;
  /** The head of the log was not read: line numbers are unknown. */
  truncated: boolean;
  loading: boolean;
  error: boolean;
}

/** The attempt named, else the run's latest. */
const attemptOf = (run: RunSummary, written: string | undefined): string | null => {
  if (written) return written;
  const ids = (run.executionHistory ?? []).map((item) => item.executionId).sort();
  return ids.at(-1) ?? null;
};

const useLogSource = (run: RunSummary, executionId: string, file: string): LogSource => {
  const stream = streamOfFile(file);
  const status = run.executionHistory?.find((item) => item.executionId === executionId)?.status;
  const coords = {
    projectId: run.projectId,
    experimentId: run.experimentId,
    runId: run.id,
    executionId,
  };
  const log = useQuery({
    ...executionLogQueryOptions(coords, stream ?? "run", {
      live: journalRefetchInterval(status) !== false,
    }),
    enabled: stream !== null,
  });
  const other = useQuery({
    ...runFileTextQueryOptions(run.projectId, run.experimentId, run.id, executionId, file),
    enabled: stream === null,
  });
  if (stream) {
    return {
      text: log.data?.text ?? null,
      truncated: log.data?.truncated ?? false,
      loading: log.isPending,
      error: log.isError,
    };
  }
  return {
    text: other.data ?? null,
    truncated: false,
    loading: other.isPending,
    error: other.isError,
  };
};

const Lines = ({ lines }: { lines: readonly ExcerptLine[] }): JSX.Element => (
  <ol className="overflow-x-auto py-2 font-mono text-label">
    {lines.map((line) => (
      <li
        key={line.number}
        className={cn("flex min-w-max", line.error && "bg-status-failed-soft text-status-failed")}
      >
        <span
          aria-hidden
          className="w-12 flex-none select-none pr-3 text-right tabular-nums text-muted-foreground"
        >
          {line.number}
        </span>
        <span className="whitespace-pre pr-3">{line.text}</span>
      </li>
    ))}
  </ol>
);

const Footer = ({
  run,
  executionId,
  file,
  range,
}: {
  run: RunSummary;
  executionId: string;
  file: string;
  range: LineRange | null;
}): JSX.Element => {
  const preview = usePreview();
  const path = runPath(run.projectId, run.experimentId, run.id, "logs", {
    attempt: executionId,
    line: range?.from ?? null,
  });
  return (
    <>
      <Terminal aria-hidden className="size-icon-sm flex-none" />
      <span className="min-w-0 truncate font-mono">
        {[runLabel(run), executionId, file].join(" · ")}
      </span>
      <button
        type="button"
        aria-label="Open in Logs"
        title="Open in Logs"
        onClick={() => preview.open(runPreviewTarget(run), { path })}
        className="ml-auto flex-none rounded-hairline hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        <ExternalLink aria-hidden className="size-icon-sm" />
      </button>
    </>
  );
};

const Excerpt = ({
  run,
  executionId,
  file,
  range,
}: {
  run: RunSummary;
  executionId: string;
  file: string;
  range: LineRange | null;
}): JSX.Element => {
  const source = useLogSource(run, executionId, file);
  if (source.loading) return <ComponentLoading name={NAME} />;
  if (source.error || source.text === null) {
    return (
      <ComponentNotice name={NAME}>
        Cannot read {file} of {executionId}.
      </ComponentNotice>
    );
  }
  if (source.truncated) {
    return (
      <ComponentNotice name={NAME}>
        {file} is longer than the browser keeps; its line numbers are only known in Logs.
      </ComponentNotice>
    );
  }
  const lines = excerptLines(source.text, range);
  return (
    <ComponentFrame
      label={`${file} of ${runLabel(run)} · ${executionId}`}
      footer={<Footer run={run} executionId={executionId} file={file} range={range} />}
    >
      {lines.length === 0 ? (
        <p className="px-3 py-2 text-label text-muted-foreground">
          {range
            ? `Lines ${range.from}–${range.to} are past the end of ${file}.`
            : `${file} is empty.`}
        </p>
      ) : (
        <Lines lines={lines} />
      )}
    </ComponentFrame>
  );
};

export const Log = ({ attrs }: DocComponentProps): JSX.Element => {
  const run = useDocRun(attrs.run);
  const range = parseLineRange(attrs.lines);
  if (!attrs.run)
    return <ComponentNotice name={NAME}>Needs a run=molab:run/… attribute.</ComponentNotice>;
  if (!run) return <ComponentNotice name={NAME}>{attrs.run} does not resolve.</ComponentNotice>;
  if (attrs.lines && !range) {
    return (
      <ComponentNotice name={NAME}>
        Cannot read lines={attrs.lines} (write 1182-1185).
      </ComponentNotice>
    );
  }
  const executionId = attemptOf(run, attrs.attempt);
  if (!executionId)
    return <ComponentNotice name={NAME}>This run has no attempt yet.</ComponentNotice>;
  return (
    <Excerpt run={run} executionId={executionId} file={attrs.file || DEFAULT_FILE} range={range} />
  );
};

export const logSpec: DocComponentSpec = {
  name: NAME,
  label: "Log excerpt",
  description: "Numbered lines of an attempt's log, error lines marked; ↗ opens Logs there",
  keywords: ["log", "excerpt", "error", "traceback", "run.log", "stdout"],
  icon: ScrollText,
  template: { run: "molab:run/", attempt: "e01", file: "run.log", lines: "" },
  Component: Log,
};
