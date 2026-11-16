/**
 * Molq run view (L14 v6): files | the picked item | no style panel (nothing
 * to style). The files are the job itself, then the attempt's scheduler files
 * under `jobs/`. The job shows its verdict line, lifetime and submission
 * facts; a file shows its text. The attempt is the host's, never picked here.
 */

import type { RunViewProps } from "@molcrafts/molab-plugin";
import {
  RunView,
  type RunViewFileItem,
  type RunViewStateSpec,
  useAttemptText,
  useRunAttempt,
  useRunLinks,
} from "@molcrafts/molab-plugin/ui";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileText } from "lucide-react";
import { type JSX, useMemo, useState } from "react";
import { StatusIcon } from "@/app/components/entity";
import { formatBytes } from "@/lib/format-bytes";
import { executorText, isMolqExecutor, jobLabel, sortSchedulerFiles } from "./job";
import { MolqFileText } from "./MolqFileText";
import { MolqDuration, MolqJob, MolqVerdict } from "./MolqJob";
import { molqExecutionQueryOptions } from "./queries";

/** The files list's first item: the job, not a file. */
export const JOB_ITEM = "job";

const message = (error: unknown): string =>
  error instanceof Error ? error.message : String(error);

export const MolqRunView = ({ files }: RunViewProps): JSX.Element => {
  const attempt = useRunAttempt();
  const { openFile } = useRunLinks();
  const record = useQuery(molqExecutionQueryOptions(attempt));
  const [picked, setPicked] = useState(JOB_ITEM);
  const scheduler = useMemo(() => sortSchedulerFiles(files), [files]);
  const file = scheduler.find((item) => item.relPath === picked) ?? null;
  const text = useAttemptText(file?.relPath ?? null);

  const executor = executorText(record.data);
  const status = record.data?.status ?? attempt.status;
  const items: RunViewFileItem[] = [
    {
      id: JOB_ITEM,
      label: jobLabel(executor),
      icon: <StatusIcon status={status} />,
      selected: !file,
    },
    ...scheduler.map((item) => ({
      id: item.relPath,
      label: item.relPath,
      meta: formatBytes(item.size),
      icon: <FileText aria-hidden className="size-icon-sm" />,
      selected: item.relPath === file?.relPath,
    })),
  ];
  const filesPanel = <RunView.Files title="Files" mode="pick" items={items} onPick={setPicked} />;

  if (file) {
    const state: RunViewStateSpec | null = text.loading
      ? { kind: "loading" }
      : text.error
        ? {
            kind: "error",
            title: `Could not read ${file.relPath}`,
            detail: text.error,
            onRetry: text.refetch,
          }
        : !text.data
          ? { kind: "empty", title: `${file.relPath} is empty` }
          : null;
    return (
      <RunView
        files={filesPanel}
        actions={
          <RunView.IconButton label={`Open ${file.relPath}`} onClick={() => openFile(file.relPath)}>
            <ExternalLink aria-hidden className="size-icon-sm" />
          </RunView.IconButton>
        }
        state={state}
      >
        <MolqFileText text={text.data ?? ""} />
      </RunView>
    );
  }

  const molq = isMolqExecutor(executor);
  const state: RunViewStateSpec | null = record.isPending
    ? { kind: "loading" }
    : record.error
      ? {
          kind: "error",
          title: "Could not read the attempt's record",
          detail: message(record.error),
          onRetry: () => void record.refetch(),
        }
      : !molq
        ? {
            kind: "empty",
            title: "Not a Molq attempt",
            detail: `${attempt.executionId} ran on ${executor.backend ?? "an unknown backend"}, not through Molq.`,
          }
        : null;
  return (
    <RunView
      files={filesPanel}
      header={molq ? <MolqVerdict status={status} executor={executor} /> : null}
      actions={molq ? <MolqDuration record={record.data} /> : null}
      state={state}
    >
      <MolqJob record={record.data} status={status} executor={executor} />
    </RunView>
  );
};
