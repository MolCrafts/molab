import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BookOpen, Download, ExternalLink, FileText, NotebookPen } from "lucide-react";
import { type JSX, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { knowledgeApi } from "@/api";
import type { NoteDetailResponse } from "@/api/generated/models/NoteDetailResponse";
import type { ReferenceSummary } from "@/api/generated/models/ReferenceSummary";
import { DashboardCanvas, EntityPage } from "@/app/components/entity";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { RendererProps } from "@/app/types";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { buildMolabRefIndex } from "@/lib/entity-linkify";
import { resolveMolabRef } from "@/lib/molab-ref";
import { DocumentControls } from "@/plugins/knowledge/DocumentControls";
import { EntityRefCard } from "@/plugins/knowledge/EntityRefCard";
import { KnowledgeDashboard } from "@/plugins/knowledge/KnowledgeDashboard";
import { NoteEditor } from "@/plugins/knowledge/NoteEditor";
import {
  knowledgeKeys,
  useKnowledgeListQuery,
  useKnowledgeNoteQuery,
} from "@/plugins/knowledge/queries";
import { TexDocumentView } from "@/plugins/knowledge/TexDocumentView";
import { isTexDocument } from "@/plugins/knowledge/texDocument";

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
  const navigate = useNavigate();
  const refIndex = useMemo(() => buildMolabRefIndex(snapshot), [snapshot]);
  const queryClient = useQueryClient();
  const listQuery = useKnowledgeListQuery();
  const data = listQuery.data;

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
  const noteError = noteQuery.error
    ? noteQuery.error instanceof Error
      ? noteQuery.error.message
      : "Failed to load note."
    : null;

  const handleSaved = (updated: NoteDetailResponse): void => {
    queryClient.setQueryData(knowledgeKeys.note(relPath), updated);
    void queryClient.invalidateQueries({ queryKey: knowledgeKeys.lists() });
  };

  const back = (): void => nav.setSelection({ objectType: "knowledge", objectId: "" });

  // --- TeX manuscript ----------------------------------------------------
  // Listed beside notes, opened with the file-preview plugin. Not a markdown note.
  if (relPath && isNotePath && isTexDocument(relPath)) {
    const fileName = relPath.split("/").pop() ?? relPath;
    return (
      <EntityPage
        icon={FileText}
        title={note?.name ?? fileName}
        actions={
          <>
            <WorkbenchIconAction label="Download TeX" asChild>
              <a href={knowledgeApi.docExportUrl(relPath)} download>
                <Download className="size-4" />
              </a>
            </WorkbenchIconAction>
            <WorkbenchIconAction label="Back to knowledge" onClick={back}>
              <ArrowLeft className="size-4" />
            </WorkbenchIconAction>
          </>
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

  // --- Note detail --------------------------------------------------------
  if (relPath && isNotePath) {
    return (
      <EntityPage
        icon={NotebookPen}
        title={note?.name ?? relPath}
        afterTitle={<DocumentControls key={relPath} relPath={relPath} placement="title" />}
        actions={
          <>
            <WorkbenchIconAction label="Export document" asChild>
              <a href={knowledgeApi.docExportUrl(relPath)} download>
                <Download className="size-4" />
              </a>
            </WorkbenchIconAction>
            <WorkbenchIconAction label="Back to knowledge" onClick={back}>
              <ArrowLeft className="size-4" />
            </WorkbenchIconAction>
          </>
        }
      >
        <div className="min-h-0 flex-1 overflow-auto">
          <DashboardCanvas>
            {noteError ? (
              <p className="text-body-lg text-destructive">{noteError}</p>
            ) : noteQuery.isPending || !note ? (
              <p className="text-body-lg italic text-muted-foreground">Loading…</p>
            ) : (
              <div className="space-y-4">
                <NoteEditor
                  note={note}
                  onSaved={handleSaved}
                  onOpenHref={(href) => {
                    const hit = resolveMolabRef(href, refIndex);
                    if (hit) navigate(hit.path);
                  }}
                />
                {note.cards && note.cards.length > 0 && (
                  <section className="space-y-2 border-t border-border/50 pt-4">
                    <h3 className="text-label font-semibold uppercase tracking-wide text-muted-foreground">
                      Embedded entities ({note.cards.length})
                    </h3>
                    <div className="space-y-2">
                      {note.cards.map((card) => (
                        <EntityRefCard
                          key={`${card.kind}:${card.id}`}
                          card={card}
                          snapshot={snapshot}
                        />
                      ))}
                    </div>
                  </section>
                )}
              </div>
            )}
          </DashboardCanvas>
        </div>
      </EntityPage>
    );
  }

  // --- Reference detail ---------------------------------------------------
  if (relPath && selectedReference) {
    const ref = selectedReference;
    return (
      <EntityPage
        icon={FileText}
        title={ref.title ?? ref.name}
        actions={
          <WorkbenchIconAction label="Back to knowledge" onClick={back}>
            <ArrowLeft className="size-4" />
          </WorkbenchIconAction>
        }
      >
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

  const notes = data?.notes ?? [];
  const references = data?.references ?? [];

  return (
    <EntityPage icon={BookOpen} title="Knowledge">
      <div className="min-h-0 flex-1 overflow-auto">
        <DashboardCanvas>
          {listQuery.isPending ? (
            <WorkbenchOperationState kind="loading" title="Loading knowledge…" skeletonRows={4} />
          ) : null}
          {listQuery.error ? (
            <WorkbenchOperationState
              kind="error"
              title="Could not load knowledge"
              detail={
                listQuery.error instanceof Error ? listQuery.error.message : "Unknown query error"
              }
              action={<WorkbenchRetryAction onClick={() => void listQuery.refetch()} />}
            />
          ) : (
            <KnowledgeDashboard
              notes={notes}
              references={references}
              onOpen={(path) => nav.setSelection({ objectType: "knowledge", objectId: path })}
            />
          )}
        </DashboardCanvas>
      </div>
    </EntityPage>
  );
};
