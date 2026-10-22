import { List } from "lucide-react";
import { type JSX, useMemo } from "react";
import { ApiError } from "@/api/generated";

import { useNavigationState } from "@/app/state/useNavigationState";
import type { RendererProps } from "@/app/types";
import { WorkbenchOperationState, WorkbenchRetryAction } from "@/components/workbench";
import { BacklinksPanel } from "@/plugins/knowledge/BacklinksPanel";
import { buildOutline, type OutlineHeading } from "@/plugins/knowledge/knowledgeDocTree";
import { useKnowledgeBacklinksQuery, useKnowledgeNoteQuery } from "@/plugins/knowledge/queries";

const INDENT_BY_LEVEL: Record<OutlineHeading["level"], string> = {
  1: "pl-2",
  2: "pl-4",
  3: "pl-6",
};

/**
 * Knowledge right-panel (inspector slot): the selected document's H1–H3 outline
 * (from the pure {@link buildOutline}) plus its clickable backlinks. With no
 * document selected it stays idle. Backlinks navigate through the shared
 * `knowledge` selection.
 */
export const KnowledgeDocPanel = ({ selection, snapshot }: RendererProps): JSX.Element | null => {
  const nav = useNavigationState(snapshot);
  const relPath = selection.objectType === "knowledge" ? selection.objectId : "";
  const noteQuery = useKnowledgeNoteQuery(relPath, Boolean(relPath));
  const backlinksQuery = useKnowledgeBacklinksQuery(relPath, Boolean(relPath));
  const outline = useMemo(
    () => (noteQuery.data ? buildOutline(noteQuery.data.body) : []),
    [noteQuery.data],
  );
  const missingNote = noteQuery.error instanceof ApiError && noteQuery.error.status === 404;
  const backlinks = backlinksQuery.data?.backlinks ?? [];

  if (!relPath) return null;

  if (noteQuery.isPending) {
    return (
      <WorkbenchOperationState
        kind="loading"
        density="compact"
        title="Loading document outline…"
        skeletonRows={3}
      />
    );
  }

  if (noteQuery.error && !missingNote) {
    return (
      <WorkbenchOperationState
        kind="error"
        density="compact"
        title="Could not load document inspector"
        detail={
          noteQuery.error instanceof Error
            ? noteQuery.error.message
            : "Failed to load knowledge document"
        }
        action={
          <WorkbenchRetryAction
            onClick={() => {
              void noteQuery.refetch();
              void backlinksQuery.refetch();
            }}
          />
        }
      />
    );
  }

  if (missingNote) return null;

  return (
    <div className="space-y-4 border-b border-border/60 p-4">
      <section className="space-y-2">
        <h3 className="flex items-center gap-2 text-label font-semibold uppercase tracking-wide text-muted-foreground">
          <List className="size-icon-sm" /> Outline
        </h3>
        {outline.length === 0 ? (
          <WorkbenchOperationState
            kind="empty"
            density="compact"
            title="No headings"
            detail="This document has no H1–H3 headings."
          />
        ) : (
          <ul className="space-y-1">
            {outline.map((heading) => (
              <li key={`${heading.slug}-${heading.level}`}>
                <a
                  href={`#${heading.slug}`}
                  className={`block truncate rounded-control py-1 text-body-lg text-foreground transition-colors hover:bg-muted/40 ${INDENT_BY_LEVEL[heading.level]}`}
                  title={heading.text}
                >
                  {heading.text}
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>
      {backlinksQuery.isPending ? (
        <WorkbenchOperationState
          kind="loading"
          density="compact"
          title="Loading backlinks…"
          skeletonRows={2}
        />
      ) : backlinksQuery.error ? (
        <WorkbenchOperationState
          kind="error"
          density="compact"
          title="Could not load backlinks"
          detail={
            backlinksQuery.error instanceof Error
              ? backlinksQuery.error.message
              : "Failed to load backlinks"
          }
          action={
            <WorkbenchRetryAction
              onClick={() => {
                void backlinksQuery.refetch();
              }}
            />
          }
        />
      ) : (
        <BacklinksPanel
          backlinks={backlinks}
          onNavigate={(target) => nav.setSelection({ objectType: "knowledge", objectId: target })}
        />
      )}
    </div>
  );
};
