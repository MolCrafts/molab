/**
 * A knowledge page's body (L10): its blocks in order, each editable in place.
 * Prose edits WYSIWYG (double-click, or the gutter pencil); an admonition,
 * tabs or a component edits as its source line(s). Edits go to the page draft;
 * a task box writes at once.
 */

import { Pencil } from "lucide-react";
import { type JSX, type KeyboardEvent, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { type DocBlock, docHeadings, keepTrailing, parseDocBlocks, toggleTaskLine } from "./blocks";
import { AdmonitionView, ComponentBlockView, TabsView } from "./DocBlocks";
import { DocMarkdown } from "./DocMarkdown";
import { INSERT_TOKEN, InlineEditor } from "./InlineEditor";

interface EditRange {
  mode: "prose" | "source";
  start: number;
  end: number;
}

const lineCount = (text: string): number => text.split("\n").length;

const splice = (body: string, start: number, end: number, text: string): string => {
  const lines = body.split("\n");
  return [...lines.slice(0, start), ...text.split("\n"), ...lines.slice(end)].join("\n");
};

/** The edited prose with the "/" token line swapped for *block*, blank lines around it. */
export const placeInsert = (markdown: string, block: string): string =>
  markdown
    .replace(new RegExp(`^.*${INSERT_TOKEN}.*$`, "m"), `\n${block}\n`)
    .replace(/\n{3,}/g, "\n\n");

/** *text* without its line *line* (the page title, drawn above the body). */
const withoutLine = (text: string, line: number | null): string =>
  line === null
    ? text
    : text
        .split("\n")
        .map((value, index) => (index === line ? "" : value))
        .join("\n");

const SourceEditor = ({
  source,
  onDone,
}: {
  source: string;
  onDone: (next: string) => void;
}): JSX.Element => {
  const [value, setValue] = useState(source);
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === "Escape") {
      event.preventDefault();
      onDone(value);
    }
  };
  return (
    <textarea
      // biome-ignore lint/a11y/noAutofocus: the user asked to edit this block
      autoFocus
      aria-label="Block source"
      value={value}
      rows={Math.max(2, lineCount(value))}
      onChange={(event) => setValue(event.target.value)}
      onBlur={() => onDone(value)}
      onKeyDown={onKeyDown}
      className="my-4 block w-full resize-none rounded-control border border-accent bg-surface p-3 font-mono text-body outline-none"
    />
  );
};

const BlockView = ({
  block,
  titleLine,
  headingIds,
  onToggleTask,
}: {
  block: DocBlock;
  titleLine: number | null;
  headingIds: readonly string[];
  onToggleTask?: (line: number) => void;
}): JSX.Element | null => {
  switch (block.kind) {
    case "markdown": {
      const local = titleLine !== null && titleLine >= block.start && titleLine < block.end;
      const text = withoutLine(block.text, local ? titleLine - block.start : null);
      if (!text.trim()) return null;
      return (
        <DocMarkdown
          text={text}
          startLine={block.start}
          headingIds={headingIds}
          onToggleTask={onToggleTask}
        />
      );
    }
    case "admonition":
      return <AdmonitionView block={block} />;
    case "tabs":
      return <TabsView block={block} />;
    case "component":
      return <ComponentBlockView block={block} />;
  }
};

export interface DocBodyProps {
  relPath: string;
  body: string;
  /** Line of the leading `# Title`, drawn as the page title instead. */
  titleLine: number | null;
  writable: boolean;
  /** Apply an edit to the latest draft; `save` writes it at once. */
  update: (edit: (body: string) => string, options?: { save?: boolean }) => void;
}

const isBlankBlock = (block: DocBlock, titleLine: number | null): boolean => {
  if (block.kind !== "markdown") return false;
  const local = titleLine !== null && titleLine >= block.start && titleLine < block.end;
  return !withoutLine(block.text, local ? titleLine - block.start : null).trim();
};

export const DocBody = ({
  relPath,
  body,
  titleLine,
  writable,
  update,
}: DocBodyProps): JSX.Element => {
  const [edit, setEditState] = useState<EditRange | null>(null);
  // The range moves as the user types; the ref keeps it exact between renders.
  const editRef = useRef<EditRange | null>(null);
  const setEdit = (next: EditRange | null): void => {
    editRef.current = next;
    setEditState(next);
  };
  /** Replace the edited range with *text* and move the range's end to match. */
  const replaceEdited = (text: string, options?: { save?: boolean; finish?: boolean }): void => {
    const range = editRef.current;
    if (!range) return;
    const { start, end } = range;
    setEdit(options?.finish ? null : { ...range, end: start + lineCount(text) });
    update((current) => splice(current, start, end, text), options);
  };
  const blocks = useMemo(() => parseDocBlocks(body), [body]);
  const headings = useMemo(() => docHeadings(blocks), [blocks]);
  const idsFor = (block: DocBlock): string[] =>
    headings.filter((h) => h.line >= block.start && h.line < block.end).map((h) => h.id);
  const lines = body.split("\n");

  const begin = (block: DocBlock): void => {
    if (!writable) return;
    setEdit({
      mode: block.kind === "markdown" ? "prose" : "source",
      start: block.start,
      end: block.end,
    });
  };
  const toggleTask = writable
    ? (line: number): void => update((current) => toggleTaskLine(current, line), { save: true })
    : undefined;

  if (!body.trim() && !edit) {
    return (
      <button
        type="button"
        disabled={!writable}
        onClick={() => setEdit({ mode: "prose", start: 0, end: lines.length })}
        className="w-full rounded-control border border-dashed border-border px-4 py-6 text-left text-doc text-muted-foreground"
      >
        Empty. Click to write; “/” inserts a block.
      </button>
    );
  }

  return (
    <div className="doc-body">
      {blocks.map((block) => {
        if (edit && block.start > edit.start && block.start < edit.end) return null;
        if (edit && block.start === edit.start) {
          const source = lines.slice(edit.start, edit.end).join("\n");
          if (edit.mode === "source") {
            return (
              <SourceEditor
                key={`edit-${edit.start}`}
                source={source}
                onDone={(next) => {
                  if (next !== source) replaceEdited(next, { finish: true });
                  else setEdit(null);
                }}
              />
            );
          }
          return (
            <InlineEditor
              key={`edit-${edit.start}`}
              relPath={relPath}
              markdown={source}
              onChange={(next) => replaceEdited(keepTrailing(source, next))}
              onDone={() => setEdit(null)}
              onInsert={(next, inserted) =>
                replaceEdited(placeInsert(next, inserted), { finish: true })
              }
            />
          );
        }
        if (isBlankBlock(block, titleLine)) return null;
        const view = (
          <BlockView
            block={block}
            titleLine={titleLine}
            headingIds={idsFor(block)}
            onToggleTask={toggleTask}
          />
        );
        return (
          // Double-click is the mouse shortcut; the gutter pencil is the keyboard way in.
          // biome-ignore lint/a11y/noStaticElementInteractions: see above
          <div
            key={`${block.kind}-${block.start}`}
            className={cn(
              "group/block relative",
              writable && block.kind === "markdown" && "cursor-text",
            )}
            onDoubleClick={block.kind === "markdown" ? () => begin(block) : undefined}
          >
            {writable ? (
              <button
                type="button"
                aria-label={block.kind === "markdown" ? "Edit" : "Edit source"}
                title={block.kind === "markdown" ? "Edit" : "Edit source"}
                onClick={() => begin(block)}
                className="absolute top-1 -left-8 flex size-6 items-center justify-center rounded-control text-muted-foreground opacity-0 group-hover/block:opacity-100 hover:bg-interactive focus-visible:opacity-100"
              >
                <Pencil aria-hidden className="size-icon-sm" />
              </button>
            ) : null}
            {view}
          </div>
        );
      })}
    </div>
  );
};
