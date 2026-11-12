/**
 * The Knowledge landing (Figma L10-1), in the L01 shape: the document count;
 * one instrument strip — Writing (documents edited per day); then the
 * documents table. No count tiles, no second filter: the side bar searches
 * and filters.
 */

import { type JSX, useMemo, useState } from "react";
import type { NoteSummary } from "@/api/generated/models/NoteSummary";
import { GaugeSection, Instrument, InstrumentStrip, OverviewCanvas } from "@/app/components/entity";
import { EditorActions } from "@/app/shell/editorActions";
import type { RendererSnapshot } from "@/app/types";
import { DialogButton } from "@/components/dialog/AppDialog";
import { formatRelative } from "@/lib/format-time";
import { CreateDocDialog, type CreateDocInput } from "./CreateDocDialog";
import { runsForHost } from "./docTemplates";
import { hostLabel } from "./hostLabel";
import { knowledgeClassOf } from "./knowledgeClass";
import { knowledgeClassIcon } from "./knowledgeClassIcon";
import { byRecent, writingDays } from "./overviewModel";
import { useKnowledgeDocs } from "./useKnowledgeDocs";
import { useHostExpansion } from "./useKnowledgeEntities";
import { WritingChart } from "./WritingChart";

const DocumentsTable = ({
  notes,
  snapshot,
  onOpen,
}: {
  notes: readonly NoteSummary[];
  snapshot: RendererSnapshot;
  onOpen: (path: string) => void;
}): JSX.Element => {
  const rows = useMemo(
    () =>
      byRecent(notes).map((note) => ({ note, where: hostLabel(snapshot, note.hostPath ?? "") })),
    [notes, snapshot],
  );
  return (
    <table className="w-full table-fixed border-collapse text-body">
      <thead>
        <tr className="h-list-row border-b border-border text-label text-muted-foreground">
          <th className="w-6" aria-label="Class" />
          <th className="text-left font-normal">Document</th>
          <th className="w-2/5 text-left font-normal max-sm:hidden">Where</th>
          <th className="w-20 text-right font-normal">Updated</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ note, where }) => {
          const Icon = knowledgeClassIcon(knowledgeClassOf(note));
          return (
            <tr
              key={note.relPath}
              onClick={() => onOpen(note.relPath)}
              className="h-list-row cursor-pointer hover:bg-interactive"
            >
              <td>
                <Icon aria-label={note.cls} className="size-icon-sm text-muted-foreground" />
              </td>
              <td className="truncate">{note.name}</td>
              <td className="truncate text-muted-foreground max-sm:hidden">{where}</td>
              <td className="text-right text-muted-foreground tabular-nums">
                {note.updatedAt ? formatRelative(note.updatedAt) : "—"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
};

export interface KnowledgeOverviewProps {
  notes: readonly NoteSummary[];
  snapshot: RendererSnapshot;
  onOpen: (path: string) => void;
}

export const KnowledgeOverview = ({
  notes,
  snapshot,
  onOpen,
}: KnowledgeOverviewProps): JSX.Element => {
  const writing = useMemo(() => writingDays(notes, Date.now()), [notes]);
  useHostExpansion(
    notes.map((note) => note.hostPath ?? ""),
    snapshot,
  );
  const { createDoc } = useKnowledgeDocs();
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const submit = async (input: CreateDocInput): Promise<void> => {
    setBusy(true);
    try {
      const relPath = await createDoc(input.name, "", input);
      setCreating(false);
      onOpen(relPath);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create document.");
    } finally {
      setBusy(false);
    }
  };

  const subject =
    notes.length === 0
      ? "No documents yet"
      : `${notes.length} ${notes.length === 1 ? "document" : "documents"}`;
  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <EditorActions>
        <DialogButton kind="primary" size="chrome" onClick={() => setCreating(true)}>
          New document
        </DialogButton>
      </EditorActions>
      <OverviewCanvas>
        <section aria-label={subject} className="min-w-0">
          <h2 className="min-w-0 truncate text-title font-semibold tabular-nums">{subject}</h2>
        </section>
        <InstrumentStrip label="Knowledge gauges">
          <Instrument
            title="Writing"
            figure={writing.reduce((sum, day) => sum + day.edits, 0)}
            caption="documents edited in 14 days"
          >
            <WritingChart days={writing} />
          </Instrument>
        </InstrumentStrip>
        <GaugeSection title="Recent" readout="newest first">
          <DocumentsTable notes={notes} snapshot={snapshot} onOpen={onOpen} />
        </GaugeSection>
      </OverviewCanvas>
      <CreateDocDialog
        open={creating}
        runs={runsForHost(snapshot.runs, "")}
        busy={busy}
        error={createError}
        onOpenChange={setCreating}
        onSubmit={submit}
      />
    </div>
  );
};
