/**
 * The Knowledge landing (Figma L10-1), in the L01 shape: a verdict about open
 * work (glyph + subject, evidence under it); one instrument strip —
 * Milestones (dial), Todos (units), Documents per class (Vega bars); then the
 * documents table and Open work. No count tiles, no second filter: the side
 * bar searches and filters.
 */

import { useQueries } from "@tanstack/react-query";
import { type JSX, useMemo, useState } from "react";
import type { NoteSummary } from "@/api/generated/models/NoteSummary";
import {
  GaugeSection,
  Instrument,
  InstrumentStrip,
  OverviewCanvas,
  StatusIcon,
  SuccessDial,
  type UnitMark,
  UnitMeter,
} from "@/app/components/entity";
import { EditorActions } from "@/app/shell/editorActions";
import type { RendererSnapshot } from "@/app/types";
import { DialogButton } from "@/components/dialog/AppDialog";
import { formatRelative } from "@/lib/format-time";
import { CreateDocDialog, type CreateDocInput } from "./CreateDocDialog";
import { runsForHost } from "./docTemplates";
import { hostLabel } from "./hostLabel";
import { knowledgeClassOf } from "./knowledgeClass";
import { knowledgeClassIcon } from "./knowledgeClassIcon";
import {
  byRecent,
  knowledgeOverview,
  type OpenWorkRow,
  RECORD_CLASSES,
  writingDays,
} from "./overviewModel";
import { knowledgeNoteQueryOptions } from "./queries";
import { useKnowledgeDocs } from "./useKnowledgeDocs";
import { useHostExpansion } from "./useKnowledgeEntities";
import { WritingChart } from "./WritingChart";

const todoMarks = (todos: { done: number; open: number; blocked: number }): UnitMark[] => [
  ...Array.from(
    { length: todos.done },
    (_, i): UnitMark => ({ key: `d${i}`, status: "succeeded", title: "Done" }),
  ),
  ...Array.from(
    { length: todos.open },
    (_, i): UnitMark => ({
      key: `o${i}`,
      status: "queued",
      title: "Open",
      outline: true,
    }),
  ),
  ...Array.from(
    { length: todos.blocked },
    (_, i): UnitMark => ({
      key: `b${i}`,
      status: "interrupted",
      title: "Blocked",
    }),
  ),
];

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
          const cls = knowledgeClassOf(note);
          const Icon = knowledgeClassIcon(cls);
          return (
            <tr
              key={note.relPath}
              onClick={() => onOpen(note.relPath)}
              className="h-list-row cursor-pointer hover:bg-interactive"
            >
              <td>
                <Icon aria-label={cls} className="size-icon-sm text-muted-foreground" />
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

const OpenWork = ({
  rows,
  onOpen,
}: {
  rows: readonly OpenWorkRow[];
  onOpen: (path: string) => void;
}): JSX.Element =>
  rows.length === 0 ? (
    <p className="text-body text-muted-foreground">Nothing open.</p>
  ) : (
    <ul className="divide-y divide-border border-b border-border">
      {rows.map((row) => (
        <li key={row.key}>
          <button
            type="button"
            onClick={() => onOpen(row.relPath)}
            className="flex min-h-10 w-full items-center gap-3 py-1 text-left hover:bg-interactive"
          >
            <StatusIcon
              status={row.status}
              label={row.status === "interrupted" ? "Blocked" : "Open"}
              className="size-icon shrink-0"
            />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-body text-foreground">{row.title}</span>
              <span className="block truncate text-label text-muted-foreground">{row.context}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );

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
  const heads = useMemo(
    () => notes.filter((note) => RECORD_CLASSES.has(knowledgeClassOf(note))),
    [notes],
  );
  const details = useQueries({
    queries: heads.map((note) => knowledgeNoteQueryOptions(note.relPath)),
  });
  const records = useMemo(
    () =>
      new Map(
        heads.flatMap((note, index) => {
          const record = details[index]?.data?.record;
          return record ? [[note.relPath, record] as const] : [];
        }),
      ),
    [heads, details],
  );
  const overview = useMemo(() => knowledgeOverview(notes, records), [notes, records]);
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

  const { verdict, todos } = overview;
  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <EditorActions>
        <DialogButton kind="primary" size="chrome" onClick={() => setCreating(true)}>
          New document
        </DialogButton>
      </EditorActions>
      <OverviewCanvas>
        <section aria-label={verdict.subject} className="min-w-0 space-y-1">
          <div className="flex min-w-0 items-center gap-2">
            <StatusIcon status={verdict.status} className="size-icon shrink-0" />
            <h2 className="min-w-0 truncate text-title font-semibold">{verdict.subject}</h2>
            <span className="ml-auto shrink-0 text-body tabular-nums">
              {notes.length} {notes.length === 1 ? "document" : "documents"}
            </span>
          </div>
          {verdict.evidence ? (
            <p className="truncate pl-6 text-body text-muted-foreground">{verdict.evidence}</p>
          ) : null}
        </section>
        <InstrumentStrip label="Knowledge gauges">
          <Instrument
            title="Milestones"
            figure={`${overview.milestoneMet} of ${overview.milestoneTotal} met`}
            inline
          >
            <SuccessDial counts={overview.milestones} />
          </Instrument>
          <Instrument
            title="Todos"
            figure={todos.done + todos.open + todos.blocked}
            caption={`${todos.done} done · ${todos.open} open · ${todos.blocked} blocked`}
          >
            <UnitMeter marks={todoMarks(todos)} label="Todos by status" emptyLabel="No todos" />
          </Instrument>
          <Instrument
            title="Writing"
            figure={writing.reduce((sum, day) => sum + day.edits, 0)}
            caption="documents edited in 14 days"
          >
            <WritingChart days={writing} />
          </Instrument>
        </InstrumentStrip>
        <div className="grid min-w-0 gap-x-12 gap-y-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <GaugeSection title="Recent" readout="newest first">
            <DocumentsTable notes={notes} snapshot={snapshot} onOpen={onOpen} />
          </GaugeSection>
          <GaugeSection title="Open work" readout="todos · delegations · milestones">
            <OpenWork rows={overview.openWork} onOpen={onOpen} />
          </GaugeSection>
        </div>
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
