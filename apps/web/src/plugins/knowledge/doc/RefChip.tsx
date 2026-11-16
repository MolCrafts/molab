/**
 * `molab:` reference as a chip (L10 `<molab-run-ref>`): a run shows its status
 * glyph and label (mono), an experiment / project / asset its kind icon and
 * name. A click previews the target (L12); a ref that no longer resolves is a
 * dashed, muted chip. Used inline (markdown links) and by components.
 */

import { Archive, Blocks, FlaskConical } from "lucide-react";
import type { JSX, MouseEvent, ReactNode } from "react";
import { StatusIcon } from "@/app/components/entity";
import { usePreview } from "@/app/preview/PreviewContext";
import type { PreviewTarget } from "@/app/preview/target";
import type { RendererSnapshot } from "@/app/types";
import { type ResolvedMolabRef, resolveMolabRef } from "@/lib/molab-ref";
import { cn } from "@/lib/utils";
import { useOptionalDoc } from "./context";

const KIND_ICON = { project: Blocks, experiment: FlaskConical, asset: Archive } as const;

export interface ResolvedRef {
  resolved: ResolvedMolabRef;
  status: string | null;
  target: PreviewTarget | null;
}

/** Resolve *ref* against the workspace snapshot: label, status, preview target. */
export const resolveDocRef = (
  ref: string,
  index: ReadonlyMap<string, import("@/lib/molab-ref").MolabRefTarget>,
  snapshot: RendererSnapshot,
): ResolvedRef | null => {
  const resolved = resolveMolabRef(ref, index);
  if (!resolved) return null;
  if (resolved.kind === "run") {
    const run = snapshot.runs.find((item) => item.ref === resolved.ref);
    return {
      resolved,
      status: run?.status ?? null,
      target: run
        ? {
            kind: "run",
            projectId: run.projectId,
            experimentId: run.experimentId,
            runId: run.id,
            ...(run.workspaceKey ? { workspaceKey: run.workspaceKey } : {}),
          }
        : null,
    };
  }
  if (resolved.kind === "experiment") {
    const exp = snapshot.experiments.find((item) => item.ref === resolved.ref);
    return {
      resolved,
      status: exp?.status ?? null,
      target: exp ? { kind: "experiment", projectId: exp.projectId, experimentId: exp.id } : null,
    };
  }
  if (resolved.kind === "project") {
    const project = snapshot.projects.find((item) => item.ref === resolved.ref);
    return {
      resolved,
      status: null,
      target: project ? { kind: "project", projectId: project.id } : null,
    };
  }
  const asset = snapshot.assets?.find((item) => item.ref === resolved.ref);
  return { resolved, status: null, target: asset ? { kind: "asset", assetId: asset.id } : null };
};

const chipClass =
  "inline-flex h-6 max-w-full items-center gap-1 rounded-control border border-border bg-surface-subtle px-2 align-middle text-body leading-none no-underline";

/** A chip for *refText*; *children* overrides the label (a link's own text). */
export const RefChip = ({
  refText,
  children,
}: {
  refText: string;
  children?: ReactNode;
}): JSX.Element => {
  const doc = useOptionalDoc();
  const preview = usePreview();
  const hit = doc ? resolveDocRef(refText, doc.refIndex, doc.snapshot) : null;
  if (!hit) {
    return (
      <span
        title={refText}
        data-molab-ref="unresolved"
        className={cn(chipClass, "border-dashed bg-transparent text-muted-foreground")}
      >
        {children ?? refText.replace(/^molab:/, "")}
      </span>
    );
  }
  const { resolved, status, target } = hit;
  const Icon = resolved.kind === "run" ? null : KIND_ICON[resolved.kind];
  const onClick = (event: MouseEvent): void => {
    if (!target) return;
    event.preventDefault();
    preview.preview(target);
  };
  const onDoubleClick = (event: MouseEvent): void => {
    if (!target) return;
    event.preventDefault();
    preview.open(target);
  };
  return (
    <a
      href={resolved.path}
      title={refText}
      data-molab-ref={resolved.kind}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      className={cn(chipClass, "text-foreground hover:border-input")}
    >
      {Icon ? (
        <Icon aria-hidden className="size-icon-sm flex-none text-muted-foreground" />
      ) : (
        <StatusIcon status={status} />
      )}
      <span className={cn("truncate", resolved.kind === "run" && !children && "font-mono")}>
        {children ?? resolved.label}
      </span>
    </a>
  );
};
