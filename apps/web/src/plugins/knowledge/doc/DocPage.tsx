/**
 * A knowledge document as one doc page (L10), as Zensical / MkDocs Material
 * draws one: the class tint fills the editor; the article (720px) carries tag
 * pills, a light title, the class line, the body and Previous / Next; "On
 * this page" sits on the right and folds under the title on a narrow page.
 */

import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CircleX, X } from "lucide-react";
import { type JSX, useMemo, useRef } from "react";
import type { NoteDetailResponse } from "@/api/generated/models/NoteDetailResponse";
import type { NoteSummary } from "@/api/generated/models/NoteSummary";
import { KnowledgeService } from "@/api/generated/services/KnowledgeService";
import { EditorActions } from "@/app/shell/editorActions";
import { useUnsavedEdits } from "@/app/shell/useUnsavedEdits";
import type { RendererSnapshot } from "@/app/types";
import { WorkbenchIconAction } from "@/components/workbench";
import { buildMolabRefIndex } from "@/lib/entity-linkify";
import { type KnowledgeClass, knowledgeClassOf } from "../knowledgeClass";
import { knowledgeKeys } from "../queries";
import { useHostExpansion, useRefExpansion } from "../useKnowledgeEntities";
import { docHeadings, parseDocBlocks } from "./blocks";
import { LinksSections } from "./components/Links";
import { DocContextProvider, type DocContextValue } from "./context";
import { DocActions } from "./DocActions";
import { ComponentBlockView } from "./DocBlocks";
import { DocBody } from "./DocBody";
import { DocHeader } from "./DocHeader";
import { DocToc, DocTocDisclosure } from "./DocToc";
import { useDocDraft } from "./useDocDraft";

/** The component that draws a class's record; drawn first when the body does not place it. */
const RECORD_COMPONENT: Partial<Record<KnowledgeClass, string>> = {
  Todo: "molab-todo-list",
  Roadmap: "molab-stage-track",
  Milestone: "molab-milestone",
  Delegation: "molab-approval",
};

/** The body's leading `# Title` line (it becomes the page title), or null. */
export const leadingTitle = (body: string): { line: number; text: string } | null => {
  const lines = body.split("\n");
  const index = lines.findIndex((line) => line.trim() !== "");
  const match = index >= 0 ? lines[index]?.match(/^#\s+(.+?)\s*#*\s*$/) : null;
  return match?.[1] ? { line: index, text: match[1] } : null;
};

/** The documents beside *relPath* on its host, in side-bar order. */
export const siblings = (
  notes: readonly NoteSummary[],
  relPath: string,
  hostPath: string,
): { prev: NoteSummary | null; next: NoteSummary | null } => {
  const row = notes
    .filter((note) => (note.hostPath ?? "") === hostPath)
    .sort((a, b) => a.name.localeCompare(b.name));
  const at = row.findIndex((note) => note.relPath === relPath);
  return {
    prev: at > 0 ? (row[at - 1] ?? null) : null,
    next: at >= 0 ? (row[at + 1] ?? null) : null,
  };
};

const PrevNext = ({
  prev,
  next,
  onOpen,
}: {
  prev: NoteSummary | null;
  next: NoteSummary | null;
  onOpen: (path: string) => void;
}): JSX.Element | null => {
  if (!prev && !next) return null;
  const card = (note: NoteSummary, word: string, forward: boolean): JSX.Element => (
    <button
      type="button"
      onClick={() => onOpen(note.relPath)}
      className={`flex min-w-0 flex-1 items-center gap-3 rounded-control border border-border bg-surface px-4 py-3 hover:border-input ${forward ? "justify-end text-right" : "text-left"}`}
    >
      {forward ? null : <ArrowLeft aria-hidden className="size-icon flex-none text-doc-accent" />}
      <span className="flex min-w-0 flex-col gap-1">
        <span className="text-label text-muted-foreground">{word}</span>
        <span className="truncate text-doc">{note.name}</span>
      </span>
      {forward ? <ArrowRight aria-hidden className="size-icon flex-none text-doc-accent" /> : null}
    </button>
  );
  return (
    <nav aria-label="Previous and next" className="mt-6 flex gap-4">
      {prev ? card(prev, "Previous", false) : <span className="flex-1" />}
      {next ? card(next, "Next", true) : <span className="flex-1" />}
    </nav>
  );
};

const longDate = (iso: string): string =>
  new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

/** MkDocs' git-revision footer: when the file last changed, and when it was made. */
const DocDates = ({
  updatedAt,
  createdAt,
}: {
  updatedAt: string | null;
  createdAt: string | null;
}): JSX.Element | null =>
  updatedAt || createdAt ? (
    <p className="mt-12 flex gap-6 border-t border-doc-accent-wash pt-3 text-label text-muted-foreground">
      {updatedAt ? <span>Last update: {longDate(updatedAt)}</span> : null}
      {createdAt ? <span>Created: {longDate(createdAt)}</span> : null}
    </p>
  ) : null;

export interface DocPageProps {
  note: NoteDetailResponse;
  summary: NoteSummary | null;
  notes: readonly NoteSummary[];
  snapshot: RendererSnapshot;
  onOpen: (path: string) => void;
}

export const DocPage = ({ note, summary, notes, snapshot, onOpen }: DocPageProps): JSX.Element => {
  const queryClient = useQueryClient();
  const scrollRef = useRef<HTMLDivElement>(null);
  const draft = useDocDraft(note);
  const cls: KnowledgeClass = knowledgeClassOf(summary ?? { cls: "Note" });
  const hostPath = summary?.hostPath ?? "";
  const title = leadingTitle(draft.body);
  const headings = useMemo(() => docHeadings(parseDocBlocks(draft.body)), [draft.body]);
  const refIndex = useMemo(() => buildMolabRefIndex(snapshot), [snapshot]);
  useHostExpansion([hostPath], snapshot);
  useRefExpansion(
    `${draft.body}\n${(note.cards ?? []).map((card) => card.ref ?? "").join("\n")}`,
    snapshot,
  );
  const { prev, next } = siblings(notes, note.relPath, hostPath);
  const writable = true;
  const recordComponent = RECORD_COMPONENT[cls];

  const leave = useUnsavedEdits({
    dirty: draft.dirty,
    saving: draft.saving,
    onSave: draft.save,
    subject: note.name,
    markPath: `/knowledge/${note.relPath.split("/").map(encodeURIComponent).join("/")}`,
  });

  const context: DocContextValue = {
    relPath: note.relPath,
    cls,
    hostPath,
    record: note.record ?? {},
    cards: note.cards ?? [],
    snapshot,
    refIndex,
    writable,
    changeBody: draft.update,
    saveRecord: async (record) => {
      const response = await KnowledgeService.replaceDocRecord(note.relPath, { record });
      queryClient.setQueryData<NoteDetailResponse>(knowledgeKeys.note(note.relPath), (current) =>
        current ? { ...current, record: response.record ?? record } : current,
      );
      void queryClient.invalidateQueries({ queryKey: knowledgeKeys.notes() });
    },
  };

  return (
    <DocContextProvider value={context}>
      <EditorActions>
        <DocActions
          relPath={note.relPath}
          cls={cls}
          name={note.name}
          hostPath={hostPath}
          status={summary?.status ?? null}
          dirty={draft.dirty}
          saving={draft.saving}
          onSave={draft.save}
          onRelocated={onOpen}
          snapshot={snapshot}
          writable={writable}
        />
      </EditorActions>
      {leave}
      <div className="flex h-full min-h-0 flex-col">
        {draft.error ? (
          <div
            role="alert"
            className="flex h-7 flex-none items-center gap-2 border-b border-status-failed/30 bg-status-failed-soft pr-2 pl-6 text-label text-status-failed-foreground"
          >
            <CircleX aria-hidden className="size-icon-sm shrink-0" />
            <span className="min-w-0 flex-1 truncate" title={draft.error}>
              {draft.error}
            </span>
            <WorkbenchIconAction label="Dismiss" onClick={draft.clearError}>
              <X aria-hidden />
            </WorkbenchIconAction>
          </div>
        ) : null}
        <div
          ref={scrollRef}
          data-class={cls.toLowerCase()}
          className="knowledge-doc @container min-h-0 flex-1 overflow-auto"
        >
          <div className="flex items-start gap-12 px-6 pt-8 pb-12 @3xl:px-12">
            <article className="w-full max-w-doc-article min-w-0 text-foreground">
              <DocHeader
                relPath={note.relPath}
                title={title?.text ?? note.name}
                cls={cls}
                status={summary?.status ?? null}
                tags={summary?.tags ?? []}
                writable={writable}
              />
              <div className="@5xl:hidden">
                <DocTocDisclosure headings={headings} />
              </div>
              {recordComponent && !draft.body.includes(recordComponent) ? (
                <ComponentBlockView
                  block={{
                    kind: "component",
                    name: recordComponent,
                    attrs: {},
                    syntax: "directive",
                    start: -1,
                    end: -1,
                    source: "",
                  }}
                />
              ) : null}
              <DocBody
                relPath={note.relPath}
                body={draft.body}
                titleLine={title?.line ?? null}
                writable={writable}
                update={draft.update}
              />
              {/molab-links/.test(draft.body) ? null : <LinksSections />}
              <DocDates updatedAt={note.updatedAt ?? null} createdAt={note.createdAt ?? null} />
              <PrevNext prev={prev} next={next} onOpen={onOpen} />
            </article>
            <aside className="sticky top-0 hidden @5xl:block">
              <DocToc headings={headings} scrollRoot={scrollRef} />
            </aside>
          </div>
        </div>
      </div>
    </DocContextProvider>
  );
};
