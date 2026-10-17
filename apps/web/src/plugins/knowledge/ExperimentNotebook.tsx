import { Download, NotebookPen, Plus } from "lucide-react";
import { type JSX, useState } from "react";
import { knowledgeApi } from "@/api";
import { EmptyState } from "@/app/components/entity";
import type { RunSummary, Selection } from "@/app/types";
import { usePrompt } from "@/components/PromptDialog";
import { WorkbenchAction } from "@/components/workbench";
import { CreateDocDialog, type CreateDocInput } from "./CreateDocDialog";
import { runsForHost } from "./docTemplates";
import { knowledgeClassOf } from "./knowledgeClass";
import { isTexDocument } from "./texDocument";
import { useKnowledgeDocs } from "./useKnowledgeDocs";

export const ExperimentNotebook = ({
  hostPath,
  runs,
  onOpen,
}: {
  hostPath: string;
  runs: RunSummary[];
  onOpen: (selection: Selection) => void;
}): JSX.Element => {
  const { notes, loading, error, createDoc, renameDoc } = useKnowledgeDocs();
  const { prompt, dialog } = usePrompt();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const docs = notes.filter(
    (note) => (note.hostPath ?? "") === hostPath && !isTexDocument(note.relPath),
  );
  const hostRuns = runsForHost(runs, hostPath);

  const submit = async (input: CreateDocInput): Promise<void> => {
    setBusy(true);
    setCreateError(null);
    try {
      const relPath = await createDoc(input.name, hostPath, input);
      setOpen(false);
      onOpen({ objectType: "knowledge", objectId: relPath });
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create document.");
    } finally {
      setBusy(false);
    }
  };

  const rename = async (path: string, current: string): Promise<void> => {
    const name = await prompt({
      title: "Rename document",
      label: "New name",
      defaultValue: current,
      confirmLabel: "Rename",
    });
    if (!name || name === current) return;
    await renameDoc(path, name);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <WorkbenchAction kind="primary" size="compact" type="button" onClick={() => setOpen(true)}>
          <Plus className="size-icon-sm" />
          New document
        </WorkbenchAction>
        <WorkbenchAction kind="ghost" size="compact" type="button" asChild>
          <a href={knowledgeApi.notebookExportUrl(hostPath)}>
            <Download className="size-icon-sm" />
            Download
          </a>
        </WorkbenchAction>
      </div>
      {error && <p className="text-label text-destructive">{error}</p>}
      {loading && docs.length === 0 ? (
        <p className="text-label text-muted-foreground">Loading documents…</p>
      ) : docs.length === 0 ? (
        <EmptyState
          icon={<NotebookPen className="h-6 w-6" />}
          title="No documents on this experiment"
          description="Write a plan, a finding, or a note beside the runs."
        />
      ) : (
        <ul className="divide-y divide-border border-y border-border">
          {docs.map((doc) => (
            <li key={doc.relPath} className="flex items-start gap-3 py-3">
              <button
                type="button"
                className="min-w-0 flex-1 text-left"
                onClick={() => onOpen({ objectType: "knowledge", objectId: doc.relPath })}
              >
                <span className="block truncate text-body-lg font-medium text-foreground">
                  {doc.name}
                </span>
                <span className="block truncate text-micro uppercase tracking-wide text-muted-foreground">
                  {knowledgeClassOf(doc)}
                </span>
                {doc.excerpt && (
                  <span className="mt-1 block truncate text-label text-muted-foreground">
                    {doc.excerpt}
                  </span>
                )}
              </button>
              <WorkbenchAction
                kind="ghost"
                size="compact"
                type="button"
                onClick={() => void rename(doc.relPath, doc.name)}
              >
                Rename
              </WorkbenchAction>
            </li>
          ))}
        </ul>
      )}
      <CreateDocDialog
        open={open}
        runs={hostRuns}
        busy={busy}
        error={createError}
        onOpenChange={setOpen}
        onSubmit={submit}
      />
      {dialog}
    </div>
  );
};
