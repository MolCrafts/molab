import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BookOpen,
  Download,
  ExternalLink,
  Eye,
  FileText,
  NotebookPen,
  Pencil,
} from "lucide-react";
import { type JSX, lazy, Suspense, useMemo, useState } from "react";
import { knowledgeApi } from "@/api";
import type { NoteDetailResponse } from "@/api/generated/models/NoteDetailResponse";
import type { ReferenceSummary } from "@/api/generated/models/ReferenceSummary";
import { EmptyState, EntityHeader } from "@/app/components/entity";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { RendererProps } from "@/app/types";
import { MarkdownContent } from "@/components/ui/markdown";
import {
  WorkbenchAction,
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
  WorkbenchToggleAction,
} from "@/components/workbench";
import { DocumentControls } from "@/plugins/knowledge/DocumentControls";
import { EntityRefCard } from "@/plugins/knowledge/EntityRefCard";
import {
  knowledgeKeys,
  useKnowledgeListQuery,
  useKnowledgeNoteQuery,
} from "@/plugins/knowledge/queries";

// Lazy-loaded so Milkdown / ProseMirror (a heavy dependency graph) is split
// into an async chunk fetched only when the user enters edit mode, keeping the
// read-only Knowledge browse path light.
const NoteEditor = lazy(() =>
  import("@/plugins/knowledge/NoteEditor").then((m) => ({ default: m.NoteEditor })),
);

const COLUMN = "mx-auto w-full max-w-3xl";

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
 * Knowledge browser — the workspace's OKF Concepts (Notes + literature
 * References). With no selection it lists everything; selecting a note's
 * bundle-relative path opens its narrative (``index.md``). Read-only: authoring
 * happens through the workspace / CLI, not the browser.
 */
export const KnowledgeViewer = ({ selection, snapshot }: RendererProps): JSX.Element => {
  const nav = useNavigationState(snapshot);
  const queryClient = useQueryClient();
  const listQuery = useKnowledgeListQuery();
  const data = listQuery.data;
  const [editingRelPath, setEditingRelPath] = useState<string | null>(null);

  const relPath = selection.objectId;
  const editing = editingRelPath === relPath;

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
    setEditingRelPath(null);
  };

  const handleEmbedded = (): void => {
    void noteQuery.refetch();
  };

  const back = (): void => nav.setSelection({ objectType: "knowledge", objectId: "" });

  // --- Note detail --------------------------------------------------------
  if (relPath && isNotePath) {
    return (
      <div className="flex h-full flex-col bg-background">
        <EntityHeader
          icon={NotebookPen}
          title={note?.name ?? relPath}
          actions={
            <>
              {note && (
                <WorkbenchToggleAction
                  label={editing ? "Preview document" : "Edit document"}
                  onClick={() => setEditingRelPath(editing ? null : relPath)}
                  pressed={editing}
                >
                  {editing ? <Eye className="size-icon" /> : <Pencil className="size-icon" />}
                </WorkbenchToggleAction>
              )}
              {/* Portable-Markdown download: a plain <a href> so the server's
                  Content-Disposition attachment header drives the browser save. */}
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
        />
        <div className={`${COLUMN} flex-1 overflow-auto px-4 py-6 md:px-8`}>
          {noteError ? (
            <p className="text-body-lg text-destructive">{noteError}</p>
          ) : noteQuery.isPending || !note ? (
            <p className="text-body-lg italic text-muted-foreground">Loading…</p>
          ) : editing ? (
            <Suspense
              fallback={
                <p className="text-body-lg italic text-muted-foreground">Loading editor…</p>
              }
            >
              <NoteEditor
                note={note}
                snapshot={snapshot}
                onSaved={handleSaved}
                onEmbedded={handleEmbedded}
              />
            </Suspense>
          ) : (
            <div className="space-y-4">
              <DocumentControls key={relPath} relPath={relPath} />
              <MarkdownContent text={note.body || "_(empty note)_"} />
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
        </div>
      </div>
    );
  }

  // --- Reference detail ---------------------------------------------------
  if (relPath && selectedReference) {
    const ref = selectedReference;
    return (
      <div className="flex h-full flex-col bg-background">
        <EntityHeader
          icon={FileText}
          title={ref.title ?? ref.name}
          actions={
            <WorkbenchIconAction label="Back to knowledge" onClick={back}>
              <ArrowLeft className="size-4" />
            </WorkbenchIconAction>
          }
        />
        <div className={`${COLUMN} flex-1 space-y-2 overflow-auto px-4 py-6 text-body-lg md:px-8`}>
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
        </div>
      </div>
    );
  }

  // --- Browse overview ----------------------------------------------------
  const notes = data?.notes ?? [];
  const references = data?.references ?? [];
  const empty = data !== undefined && notes.length === 0 && references.length === 0;

  return (
    <div className="flex h-full flex-col bg-background">
      <EntityHeader icon={BookOpen} title="Knowledge" />
      <div className={`${COLUMN} flex-1 space-y-6 overflow-auto px-4 py-6 md:px-8`}>
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
        ) : null}
        {empty && (
          <EmptyState
            icon={<BookOpen className="h-6 w-6" />}
            title="No knowledge yet"
            description="Notes and references mounted anywhere in the workspace appear here. Add them through the workspace or CLI."
          />
        )}

        {notes.length > 0 && (
          <section className="space-y-2">
            <h3 className="text-label font-semibold uppercase tracking-wide text-muted-foreground">
              Notes ({notes.length})
            </h3>
            <ul className="divide-y divide-border/50 border-y border-border/60">
              {notes.map((n) => (
                <li key={n.relPath}>
                  <WorkbenchAction
                    kind="ghost"
                    size="content"
                    type="button"
                    onClick={() =>
                      nav.setSelection({ objectType: "knowledge", objectId: n.relPath })
                    }
                    className="flex w-full items-start gap-3 px-3 py-3 text-left transition-colors hover:bg-muted/40"
                  >
                    <NotebookPen className="mt-1 size-icon flex-none text-muted-foreground" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-body-lg font-medium text-foreground">
                        {n.name}
                      </span>
                      <span className="block truncate text-label text-muted-foreground">
                        {n.excerpt.replace(/\n+/g, " ").trim() || "(empty note)"}
                      </span>
                    </span>
                  </WorkbenchAction>
                </li>
              ))}
            </ul>
          </section>
        )}

        {references.length > 0 && (
          <section className="space-y-2">
            <h3 className="text-label font-semibold uppercase tracking-wide text-muted-foreground">
              References ({references.length})
            </h3>
            <ul className="divide-y divide-border/50 border-y border-border/60">
              {references.map((r) => (
                <li key={r.relPath}>
                  <WorkbenchAction
                    kind="ghost"
                    size="content"
                    type="button"
                    onClick={() =>
                      nav.setSelection({ objectType: "knowledge", objectId: r.relPath })
                    }
                    className="flex w-full items-start gap-3 px-3 py-3 text-left transition-colors hover:bg-muted/40"
                  >
                    <FileText className="mt-1 size-icon flex-none text-muted-foreground" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-body-lg font-medium text-foreground">
                        {r.title ?? r.name}
                      </span>
                      <span className="block truncate text-label text-muted-foreground">
                        {formatReference(r)}
                      </span>
                    </span>
                  </WorkbenchAction>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
};
