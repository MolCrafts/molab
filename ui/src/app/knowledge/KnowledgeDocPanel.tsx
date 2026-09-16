import { List } from "lucide-react";
import { type JSX, useMemo } from "react";
import { ApiError } from "@/api/generated";
import { BacklinksPanel } from "@/app/knowledge/BacklinksPanel";
import { buildOutline, type OutlineHeading } from "@/app/knowledge/knowledgeDocTree";
import {
  knowledgeErrorMessage,
  selectIsNotePath,
  useKnowledgeBacklinksQuery,
  useKnowledgeListQuery,
  useKnowledgeNoteQuery,
} from "@/app/state/queries";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { RendererProps } from "@/app/types";
import { WorkbenchOperationState, WorkbenchRetryAction } from "@/components/workbench";

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
 *
 * Note-ness comes from the shared knowledge list rather than a 404 probe, and
 * the body is read through the same `knowledgeNote` key the viewer uses — so
 * opening a note costs one `getNote` round-trip for both surfaces, not two.
 */
export const KnowledgeDocPanel = ({ selection, snapshot }: RendererProps): JSX.Element | null => {
  const nav = useNavigationState(snapshot);
  const relPath = selection.objectType === "knowledge" ? selection.objectId : "";

  const listQuery = useKnowledgeListQuery();
  // `null` until the list resolves — "not yet known", distinct from "not a note".
  const isNote: boolean | null =
    relPath && listQuery.data ? selectIsNotePath(relPath)(listQuery.data) : null;

  const noteQuery = useKnowledgeNoteQuery(relPath, { enabled: isNote === true });
  const backlinksQuery = useKnowledgeBacklinksQuery(relPath, { enabled: isNote === true });

  const outline = useMemo(
    () => (noteQuery.data ? buildOutline(noteQuery.data.body) : []),
    [noteQuery.data],
  );

  if (!relPath) return null;

  // A path the list does not know as a Note (a reference, an entity concept)
  // has no outline or backlinks panel — and neither does a body that 404s.
  if (noteQuery.error instanceof ApiError && noteQuery.error.status === 404) return null;
  if (isNote === false) return null;

  if (isNote === null || (noteQuery.isPending && !noteQuery.data)) {
    const listError = listQuery.error
      ? knowledgeErrorMessage(listQuery.error, "Could not load the knowledge list")
      : null;
    if (listError) {
      return (
        <WorkbenchOperationState
          kind="error"
          density="compact"
          title="Could not load document inspector"
          detail={listError}
          action={<WorkbenchRetryAction onClick={() => void listQuery.refetch()} />}
        />
      );
    }
    return (
      <WorkbenchOperationState
        kind="loading"
        density="compact"
        title="Loading document outline…"
        skeletonRows={3}
      />
    );
  }

  if (noteQuery.error && !noteQuery.data) {
    return (
      <WorkbenchOperationState
        kind="error"
        density="compact"
        title="Could not load document inspector"
        detail={knowledgeErrorMessage(noteQuery.error, "Failed to load knowledge document")}
        action={<WorkbenchRetryAction onClick={() => void noteQuery.refetch()} />}
      />
    );
  }

  return (
    <div className="space-y-4 border-b border-border/60 p-4">
      <section className="space-y-2">
        <h3 className="flex items-center gap-2 text-label font-semibold uppercase tracking-wide text-muted-foreground">
          <List className="h-3.5 w-3.5" /> Outline
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
      {backlinksQuery.isPending && !backlinksQuery.data ? (
        <WorkbenchOperationState
          kind="loading"
          density="compact"
          title="Loading backlinks…"
          skeletonRows={2}
        />
      ) : backlinksQuery.error && !backlinksQuery.data ? (
        <WorkbenchOperationState
          kind="error"
          density="compact"
          title="Could not load backlinks"
          detail={knowledgeErrorMessage(backlinksQuery.error, "Failed to load backlinks")}
          action={<WorkbenchRetryAction onClick={() => void backlinksQuery.refetch()} />}
        />
      ) : (
        <BacklinksPanel
          backlinks={backlinksQuery.data ?? []}
          onNavigate={(target) => nav.setSelection({ objectType: "knowledge", objectId: target })}
        />
      )}
    </div>
  );
};
