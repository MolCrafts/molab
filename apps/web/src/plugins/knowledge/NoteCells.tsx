import { type JSX, type KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { knowledgeApi } from "@/api";
import type { NoteDetailResponse } from "@/api/generated/models/NoteDetailResponse";
import { MarkdownContent } from "@/components/ui/markdown";
import { cn } from "@/lib/utils";
import { joinMarkdownCells, splitMarkdownCells } from "./markdownCells";
import { buildNoteDocUpdate, isDirty } from "./noteDraft";

/**
 * Notion-style markdown: each top-level block is a cell. Double-click (or
 * Enter when focused) opens that cell for editing; blur / ⌘Enter writes
 * the whole ``index.md``.
 */
export const NoteCells = ({
  note,
  onSaved,
}: {
  note: NoteDetailResponse;
  onSaved: (updated: NoteDetailResponse) => void;
}): JSX.Element => {
  const [cells, setCells] = useState(() => splitMarkdownCells(note.body));
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const areaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setCells(splitMarkdownCells(note.body));
    setEditing(null);
  }, [note.body]);

  useEffect(() => {
    if (editing === null) return;
    const node = areaRef.current;
    if (!node) return;
    node.focus();
    node.setSelectionRange(node.value.length, node.value.length);
  }, [editing]);

  const persist = useCallback(
    async (nextCells: string[]): Promise<void> => {
      const body = joinMarkdownCells(nextCells);
      if (saving || !isDirty(note.body, body)) {
        setCells(splitMarkdownCells(note.body));
        return;
      }
      setSaving(true);
      setError(null);
      try {
        const update = buildNoteDocUpdate(note.relPath, body);
        const persisted = await knowledgeApi.editDoc(update.path, update.body);
        onSaved(persisted);
        setCells(splitMarkdownCells(persisted.body));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save note.");
        setCells(splitMarkdownCells(note.body));
      } finally {
        setSaving(false);
      }
    },
    [note.body, note.relPath, onSaved, saving],
  );

  const beginEdit = (index: number): void => {
    setEditing(index);
    setDraft(cells[index] ?? "");
    setError(null);
  };

  const commit = async (): Promise<void> => {
    if (editing === null) return;
    const index = editing;
    setEditing(null);
    const next = [...cells];
    next[index] = draft;
    const expanded = next.flatMap((cell, i) => (i === index ? splitMarkdownCells(draft) : [cell]));
    setCells(expanded);
    await persist(expanded);
  };

  const cancel = (): void => {
    setEditing(null);
    setDraft("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === "Escape") {
      event.preventDefault();
      cancel();
      return;
    }
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void commit();
    }
  };

  const addCell = (): void => {
    const next = [...cells, ""];
    setCells(next);
    setEditing(next.length - 1);
    setDraft("");
  };

  return (
    <div className="space-y-1">
      {error ? (
        <p role="alert" className="text-label text-destructive">
          {error}
        </p>
      ) : null}
      {cells.map((cell, index) => {
        const active = editing === index;
        return (
          <div
            // biome-ignore lint/suspicious/noArrayIndexKey: cells are positional document blocks
            key={`cell-${index}`}
            className={cn(
              "-mx-2 rounded-control px-2 py-1",
              active ? "bg-muted/40" : "hover:bg-muted/30",
            )}
          >
            {active ? (
              <textarea
                ref={areaRef}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onBlur={() => void commit()}
                onKeyDown={onKeyDown}
                rows={Math.max(2, draft.split("\n").length + 1)}
                aria-label={`Edit block ${index + 1}`}
                className="w-full resize-none bg-transparent text-body-lg leading-relaxed text-foreground outline-none"
              />
            ) : (
              // biome-ignore lint/a11y/noStaticElementInteractions: markdown blocks cannot live inside <button>
              <div
                className="block w-full cursor-text rounded-control text-left"
                onDoubleClick={() => beginEdit(index)}
              >
                {cell.trim().length > 0 ? (
                  <MarkdownContent text={cell} />
                ) : (
                  <span className="block min-h-7" />
                )}
              </div>
            )}
          </div>
        );
      })}
      <button
        type="button"
        onClick={addCell}
        aria-label="Add block"
        className="h-8 w-full rounded-control"
      />
    </div>
  );
};
