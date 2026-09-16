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
import { type JSX, lazy, Suspense, useEffect, useMemo, useState } from "react";
import type { NoteSummary } from "@/api/generated/models/NoteSummary";
import type { ReferenceSummary } from "@/api/generated/models/ReferenceSummary";
import { EmptyState, EntityHeader } from "@/app/components/entity";
import { DocumentControls } from "@/app/renderers/knowledge/DocumentControls";
import { EntityRefCard } from "@/app/renderers/knowledge/EntityRefCard";
import { workspaceApi } from "@/app/state/api";
import {
  knowledgeErrorMessage,
  useInvalidate,
  useKnowledgeListQuery,
  useKnowledgeNotePrefetch,
  useKnowledgeNoteQuery,
} from "@/app/state/queries";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { RendererProps, Selection } from "@/app/types";
import { MarkdownContent } from "@/components/ui/markdown";
import {
  WorkbenchAction,
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
  WorkbenchToggleAction,
} from "@/components/workbench";

// Lazy-loaded so Milkdown / ProseMirror (a heavy dependency graph) is split
// into an async chunk fetched only when the user enters edit mode, keeping the
// read-only Knowledge browse path light.
const NoteEditor = lazy(() =>
  import("@/app/renderers/knowledge/NoteEditor").then((m) => ({ default: m.NoteEditor })),
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

interface NoteRowProps {
  note: NoteSummary;
  onSelect: (selection: Selection) => void;
}

/** One note in the browse list; hover/focus warms its body for the click. */
const NoteRow = ({ note, onSelect }: NoteRowProps): JSX.Element => {
  const prefetch = useKnowledgeNotePrefetch(note.relPath);
  return (
    <WorkbenchAction
      kind="ghost"
      size="content"
      type="button"
      onClick={() => onSelect({ objectType: "knowledge", objectId: note.relPath })}
      className="flex w-full items-start gap-3 px-3 py-3 text-left transition-colors hover:bg-muted/40"
      {...prefetch}
    >
      <NotebookPen className="mt-1 h-4 w-4 flex-none text-muted-foreground" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-body-lg font-medium text-foreground">{note.name}</span>
        <span className="block truncate text-label text-muted-foreground">
          {note.excerpt.replace(/\n+/g, " ").trim() || "(empty note)"}
        </span>
      </span>
    </WorkbenchAction>
  );
};

/**
 * Knowledge browser — the workspace's OKF Concepts (Notes + literature
 * References). With no selection it lists everything; selecting a note's
 * bundle-relative path opens its narrative (``index.md``). Read-only: authoring
 * happens through the workspace / CLI, not the browser.
 */
export const KnowledgeViewer = ({ selection, snapshot }: RendererProps): JSX.Element => {
  const nav = useNavigationState(snapshot);
  const { afterNoteMutation } = useInvalidate();
  const [editing, setEditing] = useState<boolean>(false);

  const relPath = selection.objectId;

  // The one shared knowledge list — the doc tree, its facets and the command
  // palette read this same cache entry, so entering Knowledge costs one request.
  const listQuery = useKnowledgeListQuery();
  const data = listQuery.data ?? null;
  const error = listQuery.error
    ? knowledgeErrorMessage(listQuery.error, "Failed to load knowledge.")
    : null;

  // The selected reference (if the path names one) comes from the list directly.
  const selectedReference = useMemo(
    () => data?.references.find((r) => r.relPath === relPath) ?? null,
    [data, relPath],
  );
  const isNotePath = useMemo(
    () => Boolean(relPath) && Boolean(data?.notes.some((n) => n.relPath === relPath)),
    [data, relPath],
  );

  // The body shares its key with the inspector panel, so both surfaces are
  // served by one `getNote` round-trip.
  const noteQuery = useKnowledgeNoteQuery(relPath, { enabled: isNotePath });
  const note = noteQuery.data ?? null;
  const noteError = noteQuery.error
    ? knowledgeErrorMessage(noteQuery.error, "Failed to load note.")
    : null;

  // Editing is a note-local affordance: any selection change returns to preview.
  // biome-ignore lint/correctness/useExhaustiveDependencies: relPath is the reset trigger, not a read
  useEffect(() => {
    setEditing(false);
  }, [relPath]);

  /** A save/embed realigns the body (and the list's excerpt) with the server. */
  const afterWrite = (): void => {
    setEditing(false);
    void afterNoteMutation(relPath);
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
                  onClick={() => setEditing((prev) => !prev)}
                  pressed={editing}
                >
                  {editing ? <Eye className="h-4 w-4" /> : <Pencil className="h-4 w-4" />}
                </WorkbenchToggleAction>
              )}
              {/* Portable-Markdown download: a plain <a href> so the server's
                  Content-Disposition attachment header drives the browser save. */}
              <WorkbenchIconAction label="Export document" asChild>
                <a href={workspaceApi.knowledgeDocExportUrl(relPath)} download>
                  <Download className="h-4 w-4" />
                </a>
              </WorkbenchIconAction>
              <WorkbenchIconAction label="Back to knowledge" onClick={back}>
                <ArrowLeft className="h-4 w-4" />
              </WorkbenchIconAction>
            </>
          }
        />
        <div className={`${COLUMN} flex-1 overflow-auto px-4 py-6 md:px-8`}>
          {noteError && !note ? (
            <WorkbenchOperationState
              kind="error"
              density="compact"
              title="Could not load note"
              detail={noteError}
              action={<WorkbenchRetryAction onClick={() => void noteQuery.refetch()} />}
            />
          ) : !note ? (
            <WorkbenchOperationState
              kind="loading"
              density="compact"
              title="Loading note…"
              skeletonRows={6}
            />
          ) : editing ? (
            <Suspense
              fallback={
                <WorkbenchOperationState
                  kind="loading"
                  density="compact"
                  title="Loading editor…"
                  skeletonRows={6}
                />
              }
            >
              <NoteEditor
                note={note}
                snapshot={snapshot}
                onSaved={afterWrite}
                onEmbedded={afterWrite}
              />
            </Suspense>
          ) : (
            <div className="space-y-4">
              <DocumentControls relPath={relPath} />
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
              <ArrowLeft className="h-4 w-4" />
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
                <ExternalLink className="h-3.5 w-3.5" /> {ref.url}
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
  const empty = data !== null && notes.length === 0 && references.length === 0;

  return (
    <div className="flex h-full flex-col bg-background">
      <EntityHeader
        icon={BookOpen}
        title="Knowledge"
        subtitle="Notes and literature references for this workspace (OKF concepts)."
      />
      <div className={`${COLUMN} flex-1 space-y-6 overflow-auto px-4 py-6 md:px-8`}>
        {error && (
          <WorkbenchOperationState
            kind="error"
            density="compact"
            title="Could not load knowledge"
            detail={error}
            action={<WorkbenchRetryAction onClick={() => void listQuery.refetch()} />}
          />
        )}
        {listQuery.isPending && !data && (
          <WorkbenchOperationState
            kind="loading"
            density="compact"
            title="Loading knowledge…"
            skeletonRows={5}
          />
        )}
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
                  <NoteRow note={n} onSelect={nav.setSelection} />
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
                    <FileText className="mt-1 h-4 w-4 flex-none text-muted-foreground" />
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
