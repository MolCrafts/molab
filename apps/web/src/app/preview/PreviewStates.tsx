/**
 * Preview states (Figma L12-10). While the state is unknown the header shows
 * the kind's icon, never a status glyph: a loading run has no verdict yet.
 */

import { CircleAlert } from "lucide-react";
import type { JSX } from "react";
import { entityMeta } from "@/app/entities/kinds";
import type { SemanticObjectType } from "@/app/types";
import { WorkbenchAction } from "@/components/workbench";
import { KindIcon, PreviewFrame } from "./PreviewFrame";

interface StateProps {
  title: string;
  mono?: boolean;
  kindLabel: string;
  onOpen: () => void;
  onClose: () => void;
}

const KIND_OF: Record<string, SemanticObjectType> = {
  run: "run",
  attempt: "run",
  task: "task",
  experiment: "experiment",
  project: "project",
  asset: "asset",
  file: "workspace-file",
  document: "knowledge",
};

const lead = (kindLabel: string): JSX.Element => (
  <KindIcon icon={entityMeta(KIND_OF[kindLabel] ?? "run").icon} />
);

export const PreviewLoading = ({ kindLabel, ...frame }: StateProps): JSX.Element => (
  <PreviewFrame {...frame} lead={lead(kindLabel)} context={kindLabel}>
    <div role="status" aria-label={`Loading ${frame.title}`} className="space-y-2">
      <div className="h-px w-full overflow-hidden bg-border">
        <div className="mol-status-progress-indeterminate h-full w-1/3 bg-accent" />
      </div>
      <p className="text-label text-muted-foreground">Loading {frame.title} …</p>
    </div>
  </PreviewFrame>
);

export const PreviewGone = ({ kindLabel, ...frame }: StateProps): JSX.Element => (
  <PreviewFrame {...frame} lead={lead(kindLabel)} context={kindLabel}>
    <p className="text-body">This {kindLabel} no longer exists.</p>
    <p className="text-label text-muted-foreground">
      It was removed after the list was read. The list refreshes on its own.
    </p>
  </PreviewFrame>
);

export const PreviewError = ({
  kindLabel,
  message,
  onRetry,
  ...frame
}: StateProps & { message: string; onRetry: () => void }): JSX.Element => (
  <PreviewFrame
    {...frame}
    lead={lead(kindLabel)}
    context={kindLabel}
    actions={
      <WorkbenchAction
        kind="secondary"
        size="content"
        className="h-shell-button rounded-hairline bg-interactive px-3 font-normal"
        onClick={onRetry}
      >
        Retry
      </WorkbenchAction>
    }
  >
    <p className="flex items-center gap-2 text-body">
      <CircleAlert className="size-icon flex-none text-destructive" aria-hidden />
      Couldn’t load this {kindLabel}
    </p>
    <p className="pl-6 text-label text-muted-foreground">{message}</p>
  </PreviewFrame>
);
