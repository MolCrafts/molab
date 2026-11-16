import { Download, ExternalLink, FileText } from "lucide-react";
import { type JSX, useMemo, useState } from "react";
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
import { KNOWLEDGE_CLASS_ICON } from "@/plugins/knowledge/knowledgeClassIcon";
import {
  useKnowledgeBibliographyQuery,
  useKnowledgeListQuery,
  useKnowledgeNoteQuery,
  useKnowledgeVersionsQuery,
} from "@/plugins/knowledge/queries";
import { TexDocumentView } from "@/plugins/knowledge/TexDocumentView";
import { bibliographyName, isTexDocument, withBibliography } from "@/plugins/knowledge/texDocument";
import { DocPage } from "./doc/DocPage";
import { VersionBanner, VersionDiff, VersionSwitcher } from "./doc/DocVersions";

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
 * File-based knowledge browser. Project plugins open separately; selecting
 * a document opens its narrative as editable cells.
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
  /** The git version the URL asks for; null is the live file. */
  const version = selection.objectType === "knowledge" ? (selection.version ?? null) : null;
  /** The `path@version` whose diff is open in place of the Manuscript. */
  const [comparing, setComparing] = useState<string | null>(null);

  // The selected reference (if the path names one) comes from the list directly.
  const selectedReference = useMemo(
    () => data?.references.find((r) => r.relPath === relPath) ?? null,
    [data, relPath],
  );
  const isNotePath = useMemo(
    () => Boolean(relPath) && Boolean(data?.notes.some((n) => n.relPath === relPath)),
    [data, relPath],
  );
  const noteQuery = useKnowledgeNoteQuery(relPath, isNotePath, version);
  const note = noteQuery.data ?? null;
  const isManuscript = relPath !== "" && isNotePath && isTexDocument(relPath);
  const versionsQuery = useKnowledgeVersionsQuery(relPath, isManuscript);
  const history = versionsQuery.data?.available ? versionsQuery.data : null;
  const bibliographyQuery = useKnowledgeBibliographyQuery(
    relPath,
    isManuscript && note !== null && bibliographyName(note.body) !== null,
  );
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
  const showVersion = (next: number | null): void =>
    nav.setSelection({
      objectType: "knowledge",
      objectId: relPath,
      ...(next === null ? {} : { version: next }),
    });
  const versionKey = `${relPath}@${version}`;

  // --- Manuscript ----------------------------------------------------------
  // A LaTeX document: opened with the file-preview plugin, not the markdown page.
  if (relPath && isNotePath && isTexDocument(relPath)) {
    const fileName = relPath.split("/").pop() ?? relPath;
    return (
      <EntityPage
        icon={KNOWLEDGE_CLASS_ICON.Manuscript}
        title={note?.name ?? fileName}
        actions={
          <>
            {history && history.versions.length > 0 ? (
              <VersionSwitcher
                history={history}
                viewing={version}
                disabledReason={null}
                onSelect={showVersion}
              />
            ) : null}
            <WorkbenchIconAction label="Download TeX" asChild>
              <a href={knowledgeApi.docExportUrl(relPath)} download>
                <Download className="size-4" />
              </a>
            </WorkbenchIconAction>
          </>
        }
      >
        <div className="flex min-h-0 flex-1 flex-col">
          {version !== null ? (
            <div className="px-4 pt-4">
              <VersionBanner
                history={history}
                version={version}
                comparing={comparing === versionKey}
                onCompare={(on) => setComparing(on ? versionKey : null)}
                onLatest={() => showVersion(null)}
              />
            </div>
          ) : null}
          {version !== null && comparing === versionKey ? (
            <div className="min-h-0 flex-1 overflow-auto px-4 pb-4">
              <VersionDiff relPath={relPath} version={version} />
            </div>
          ) : (
            <div className="min-h-0 flex-1">
              {noteError ? (
                <p className="px-4 py-6 text-body-lg text-destructive">{noteError}</p>
              ) : noteQuery.isPending || !note ? (
                <p className="px-4 py-6 text-body-lg italic text-muted-foreground">Loading…</p>
              ) : (
                <TexDocumentView
                  content={
                    bibliographyQuery.data === undefined
                      ? note.body
                      : withBibliography(note.body, bibliographyQuery.data)
                  }
                  name={fileName}
                  path={relPath}
                />
              )}
            </div>
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
        key={versionKey}
        version={version}
        onVersion={showVersion}
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
  return (
    <WorkbenchOperationState
      kind="empty"
      title="No document selected"
      detail="Choose a file from the explorer. Select a project to open its Relations tab."
    />
  );
};
