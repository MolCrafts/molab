import { Download, ExternalLink, FileText } from "lucide-react";
import { type JSX, useMemo } from "react";
import { knowledgeApi } from "@/api";
import { activeNeedsAuth, shouldShowFailure } from "@/api/errors";
import type { ReferenceSummary } from "@/api/generated/models/ReferenceSummary";
import { DashboardCanvas, EntityPage } from "@/app/components/entity";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { RendererProps } from "@/app/types";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { useKnowledgeListQuery, useKnowledgeNoteQuery } from "@/plugins/knowledge/queries";
import { TexDocumentView } from "@/plugins/knowledge/TexDocumentView";
import { isTexDocument } from "@/plugins/knowledge/texDocument";
import { DocPage } from "./doc/DocPage";
import { KnowledgeOverview } from "./KnowledgeOverview";

const formatReference = (ref: ReferenceSummary): string => {
  const authors =
    ref.authors && ref.authors.length > 0
      ? ref.authors.length > 3
        ? `${ref.authors.slice(0, 3).join(", ")} et al.`
        : ref.authors.join(", ")
      : "";
  const bits = [authors, ref.year ? `(${ref.year})` : "", ref.venue ?? ""].filter(Boolean);
  return bits.join(" · ");
};

/**
 * Knowledge browser. With no selection it shows a class dashboard; selecting
 * a document opens its narrative as Notion-style cells (double-click to edit).
 */
export const KnowledgeViewer = ({ selection, snapshot }: RendererProps): JSX.Element => {
  const nav = useNavigationState(snapshot);
  const listQuery = useKnowledgeListQuery();
  const data = listQuery.data;
  const needsAuth = activeNeedsAuth(snapshot.workspaces);
  const knowledgeFailed = shouldShowFailure(listQuery.error, {
    fetching: listQuery.isPending || listQuery.isFetching,
    needsAuth,
  });

  const relPath = selection.objectId;

  // The selected reference (if the path names one) comes from the list directly.
  const selectedReference = useMemo(
    () => data?.references.find((r) => r.relPath === relPath) ?? null,
    [data, relPath],
  );
  const isNotePath = useMemo(
    () => Boolean(relPath) && Boolean(data?.notes.some((n) => n.relPath === relPath)),
    [data, relPath],
  );
  const noteQuery = useKnowledgeNoteQuery(relPath, isNotePath);
  const note = noteQuery.data ?? null;
  const noteError = shouldShowFailure(noteQuery.error, {
    fetching: noteQuery.isFetching,
    needsAuth,
  })
    ? noteQuery.error instanceof Error
      ? noteQuery.error.message
      : "Failed to load note."
    : null;

  const open = (path: string): void =>
    nav.setSelection({ objectType: "knowledge", objectId: path });

  // --- TeX manuscript ----------------------------------------------------
  // Listed beside notes, opened with the file-preview plugin. Not a markdown note.
  if (relPath && isNotePath && isTexDocument(relPath)) {
    const fileName = relPath.split("/").pop() ?? relPath;
    return (
      <EntityPage
        icon={FileText}
        title={note?.name ?? fileName}
        actions={
          <WorkbenchIconAction label="Download TeX" asChild>
            <a href={knowledgeApi.docExportUrl(relPath)} download>
              <Download className="size-4" />
            </a>
          </WorkbenchIconAction>
        }
      >
        <div className="min-h-0 flex-1">
          {noteError ? (
            <p className="px-4 py-6 text-body-lg text-destructive">{noteError}</p>
          ) : noteQuery.isPending || !note ? (
            <p className="px-4 py-6 text-body-lg italic text-muted-foreground">Loading…</p>
          ) : (
            <TexDocumentView content={note.body} name={fileName} path={relPath} />
          )}
        </div>
      </EntityPage>
    );
  }

  // --- Note detail: one doc page (L10) ------------------------------------
  if (relPath && isNotePath) {
    if (noteError) {
      return (
        <WorkbenchOperationState
          kind="error"
          title="Could not load the document"
          detail={noteError}
          action={<WorkbenchRetryAction onClick={() => void noteQuery.refetch()} />}
        />
      );
    }
    if (noteQuery.isPending || !note) {
      return <WorkbenchOperationState kind="loading" title="Loading document…" skeletonRows={6} />;
    }
    return (
      <DocPage
        note={note}
        summary={data?.notes.find((row) => row.relPath === relPath) ?? null}
        notes={data?.notes ?? []}
        snapshot={snapshot}
        onOpen={open}
      />
    );
  }

  // --- Reference detail ---------------------------------------------------
  if (relPath && selectedReference) {
    const ref = selectedReference;
    return (
      <EntityPage icon={FileText} title={ref.title ?? ref.name}>
        <div className="min-h-0 flex-1 overflow-auto text-body-lg">
          <DashboardCanvas>
            <p className="text-muted-foreground">{formatReference(ref)}</p>
            {ref.doi && (
              <p>
                DOI:{" "}
                <a
                  className="text-info hover:underline"
                  href={`https://doi.org/${ref.doi}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {ref.doi}
                </a>
              </p>
            )}
            {ref.url && (
              <p>
                <a
                  className="inline-flex items-center gap-1 text-info hover:underline"
                  href={ref.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink className="size-icon-sm" /> {ref.url}
                </a>
              </p>
            )}
            <p className="text-label text-muted-foreground">source: {ref.source}</p>
          </DashboardCanvas>
        </div>
      </EntityPage>
    );
  }

  if (listQuery.isPending || (needsAuth && !data)) {
    return <WorkbenchOperationState kind="loading" title="Loading knowledge…" skeletonRows={4} />;
  }
  if (knowledgeFailed) {
    return (
      <WorkbenchOperationState
        kind="error"
        title="Could not load knowledge"
        detail={listQuery.error instanceof Error ? listQuery.error.message : "Unknown query error"}
        action={<WorkbenchRetryAction onClick={() => void listQuery.refetch()} />}
      />
    );
  }
  return <KnowledgeOverview notes={data?.notes ?? []} snapshot={snapshot} onOpen={open} />;
};
