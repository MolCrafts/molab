/**
 * A knowledge document's body as blocks (L10): markdown, MkDocs admonitions
 * (`!!! type "title"`, `???` folds, `???+` folds open), MkDocs content tabs
 * (`=== "Label"`), and `<molab-…>` components written either as a leaf
 * directive (`::molab-run-table{experiment=…}`) or as a one-line HTML element.
 *
 * Every block keeps its exact source lines, so an edit replaces only the
 * lines of the block it touched and the rest of the file is never rewritten.
 */

export type AdmonitionFold = "none" | "open" | "closed";

interface BlockBase {
  /** First source line (0-based). */
  start: number;
  /** One past the last source line. */
  end: number;
  /** The block's lines, exactly as written. */
  source: string;
}

export interface MarkdownBlock extends BlockBase {
  kind: "markdown";
  text: string;
}

export interface AdmonitionBlock extends BlockBase {
  kind: "admonition";
  type: string;
  title: string | null;
  fold: AdmonitionFold;
  body: string;
}

export interface TabsBlock extends BlockBase {
  kind: "tabs";
  tabs: { label: string; body: string }[];
}

export interface ComponentBlock extends BlockBase {
  kind: "component";
  name: string;
  attrs: Record<string, string>;
  syntax: "directive" | "html";
}

export type DocBlock = MarkdownBlock | AdmonitionBlock | TabsBlock | ComponentBlock;

const FENCE = /^ {0,3}(`{3,}|~{3,})/;
const ADMONITION = /^(!!!|\?\?\?\+?)\s+([A-Za-z][\w-]*)(?:\s+"([^"]*)")?\s*$/;
const TAB = /^===\+?\s+"([^"]*)"\s*$/;
const DIRECTIVE = /^::(molab-[a-z][a-z0-9-]*)(?:\{(.*)\})?\s*$/;
const HTML_COMPONENT =
  /^<(molab-[a-z][a-z0-9-]*)((?:\s+[\w-]+(?:=(?:"[^"]*"|'[^']*'|[^\s>"']+))?)*)\s*(?:\/>|>\s*<\/\1>)\s*$/;
const INDENT = /^( {4}|\t)/;
/** `<molab-markdown>` / `</molab-markdown>` alone on a line: the prose wrapper of an HTML document. */
const MARKDOWN_WRAPPER = /^\s*<\/?molab-markdown\s*>\s*$/;
const ATTR = /([\w-]+)(?:=("[^"]*"|'[^']*'|[^\s"']+))?/g;

const isBlank = (line: string): boolean => line.trim() === "";

/** `a=1 b="two words" flag` → `{ a: "1", b: "two words", flag: "true" }`. */
export const parseAttrs = (text: string): Record<string, string> => {
  const attrs: Record<string, string> = {};
  for (const match of text.matchAll(ATTR)) {
    const key = match[1];
    if (!key) continue;
    const raw = match[2];
    attrs[key] =
      raw === undefined
        ? "true"
        : raw
            .replace(/^(["'])(.*)\1$/, "$2")
            .replace(/&quot;/g, '"')
            .replace(/&lt;/g, "<")
            .replace(/&amp;/g, "&");
  }
  return attrs;
};

/** The indented body after a header line: indented or blank lines, minus trailing blanks. */
const indentedBody = (lines: string[], from: number): number => {
  let end = from;
  let last = from;
  while (end < lines.length) {
    const line = lines[end] ?? "";
    if (isBlank(line)) {
      end += 1;
      continue;
    }
    if (!INDENT.test(line)) break;
    end += 1;
    last = end;
  }
  return last;
};

const dedent = (lines: string[]): string =>
  lines
    .map((line) => line.replace(INDENT, ""))
    .join("\n")
    .replace(/^\n+|\n+$/g, "");

const make = <T extends DocBlock>(
  lines: string[],
  start: number,
  end: number,
  fields: Omit<T, keyof BlockBase>,
): T => ({ ...fields, start, end, source: lines.slice(start, end).join("\n") }) as T;

/** Parse a document body into blocks. Joining every block's `source` with "\n" gives the body back. */
export const parseDocBlocks = (body: string): DocBlock[] => {
  const lines = body.replace(/\r\n?/g, "\n").split("\n");
  const blocks: DocBlock[] = [];
  let mdStart: number | null = null;
  let fence: string | null = null;

  const flushMarkdown = (end: number): void => {
    if (mdStart === null) return;
    blocks.push(
      make<MarkdownBlock>(lines, mdStart, end, {
        kind: "markdown",
        text: lines.slice(mdStart, end).join("\n"),
      }),
    );
    mdStart = null;
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    const marker = line.match(FENCE);
    if (fence !== null) {
      if (marker?.[1] && marker[1][0] === fence[0] && marker[1].length >= fence.length)
        fence = null;
      i += 1;
      continue;
    }
    if (marker?.[1]) {
      mdStart ??= i;
      fence = marker[1];
      i += 1;
      continue;
    }

    // A wrapper line is its own (invisible) block, so editing the prose inside
    // an HTML document never touches the wrapper.
    if (MARKDOWN_WRAPPER.test(line)) {
      flushMarkdown(i);
      blocks.push(make<MarkdownBlock>(lines, i, i + 1, { kind: "markdown", text: line }));
      i += 1;
      continue;
    }

    const adm = line.match(ADMONITION);
    if (adm) {
      flushMarkdown(i);
      const end = indentedBody(lines, i + 1);
      const fold: AdmonitionFold =
        adm[1] === "!!!" ? "none" : adm[1] === "???+" ? "open" : "closed";
      blocks.push(
        make<AdmonitionBlock>(lines, i, end, {
          kind: "admonition",
          type: (adm[2] ?? "note").toLowerCase(),
          title: adm[3] ?? null,
          fold,
          body: dedent(lines.slice(i + 1, end)),
        }),
      );
      i = end;
      continue;
    }

    if (TAB.test(line)) {
      flushMarkdown(i);
      const tabs: { label: string; body: string }[] = [];
      const start = i;
      let end = i;
      let cursor = i;
      while (cursor < lines.length) {
        const header = (lines[cursor] ?? "").match(TAB);
        if (!header) break;
        const bodyEnd = indentedBody(lines, cursor + 1);
        tabs.push({ label: header[1] ?? "", body: dedent(lines.slice(cursor + 1, bodyEnd)) });
        end = bodyEnd;
        let next = bodyEnd;
        while (next < lines.length && isBlank(lines[next] ?? "")) next += 1;
        if (!TAB.test(lines[next] ?? "")) break;
        cursor = next;
      }
      blocks.push(make<TabsBlock>(lines, start, end, { kind: "tabs", tabs }));
      i = end;
      continue;
    }

    const directive = line.match(DIRECTIVE);
    const html = directive ? null : line.match(HTML_COMPONENT);
    if (directive || html) {
      flushMarkdown(i);
      const name = (directive?.[1] ?? html?.[1] ?? "").toLowerCase();
      blocks.push(
        make<ComponentBlock>(lines, i, i + 1, {
          kind: "component",
          name,
          attrs: parseAttrs((directive ? directive[2] : html?.[2]) ?? ""),
          syntax: directive ? "directive" : "html",
        }),
      );
      i += 1;
      continue;
    }

    mdStart ??= i;
    i += 1;
  }
  flushMarkdown(lines.length);
  return blocks;
};

const splice = (body: string, start: number, end: number, text: string | null): string => {
  const lines = body.replace(/\r\n?/g, "\n").split("\n");
  const next = text === null ? [] : text.split("\n");
  return [...lines.slice(0, start), ...next, ...lines.slice(end)].join("\n");
};

/** The body with *block*'s lines replaced by *text*. */
export const replaceBlock = (body: string, block: DocBlock, text: string): string =>
  splice(body, block.start, block.end, text);

/** The body without *block*. */
export const removeBlock = (body: string, block: DocBlock): string =>
  splice(body, block.start, block.end, null).replace(/\n{3,}/g, "\n\n");

/** The body with *text* inserted after *block*, one blank line on each side. */
export const insertAfterBlock = (body: string, block: DocBlock, text: string): string => {
  const lines = body.replace(/\r\n?/g, "\n").split("\n");
  let end = block.end;
  while (end > block.start && isBlank(lines[end - 1] ?? "")) end -= 1;
  const tail = lines.slice(end);
  while (tail.length > 0 && isBlank(tail[0] ?? "")) tail.shift();
  const parts = [...lines.slice(0, end), "", ...text.split("\n")];
  return (tail.length > 0 ? [...parts, "", ...tail] : parts).join("\n");
};

/** The body with *text* appended as a new block. */
export const appendBlock = (body: string, text: string): string => {
  const trimmed = body.replace(/\s+$/, "");
  return trimmed ? `${trimmed}\n\n${text}\n` : `${text}\n`;
};

/** A leaf directive: `::molab-run-ref{ref=molab:run/abc label="ase nve"}`. */
export const formatComponent = (name: string, attrs: Record<string, string>): string => {
  const parts = Object.entries(attrs).map(([key, value]) =>
    /^[^\s"'{}]+$/.test(value) ? `${key}=${value}` : `${key}="${value.replace(/"/g, "&quot;")}"`,
  );
  return parts.length > 0 ? `::${name}{${parts.join(" ")}}` : `::${name}`;
};

const TASK = /^(\s*[-*+]\s+\[)([ xX])(\]\s)/;

/** Flip the GFM task box on *line*; any other line leaves the body as it was. */
export const toggleTaskLine = (body: string, line: number): string => {
  const lines = body.split("\n");
  const current = lines[line];
  if (current === undefined || !TASK.test(current)) return body;
  lines[line] = current.replace(
    TASK,
    (_m, open: string, mark: string, close: string) => `${open}${mark.trim() ? " " : "x"}${close}`,
  );
  return lines.join("\n");
};

export interface DocHeading {
  level: 2 | 3;
  text: string;
  id: string;
  /** Source line of the heading (0-based). */
  line: number;
}

const slug = (text: string): string =>
  text
    .toLowerCase()
    .replace(/[`*_~[\]()]/g, "")
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .trim()
    .replace(/\s+/g, "-") || "section";

const HEADING = /^(#{2,3})\s+(.+?)\s*#*\s*$/;

/** The page's h2 / h3 (top-level markdown only), with unique anchor ids. */
export const docHeadings = (blocks: readonly DocBlock[]): DocHeading[] => {
  const seen = new Map<string, number>();
  const out: DocHeading[] = [];
  for (const block of blocks) {
    if (block.kind !== "markdown") continue;
    let fence: string | null = null;
    block.text.split("\n").forEach((line, offset) => {
      const marker = line.match(FENCE);
      if (fence !== null) {
        if (marker?.[1] && marker[1][0] === fence[0]) fence = null;
        return;
      }
      if (marker?.[1]) {
        fence = marker[1];
        return;
      }
      const match = line.match(HEADING);
      if (!match?.[1] || !match[2]) return;
      const text = match[2].replace(/[`*_]/g, "");
      const base = slug(text);
      const count = seen.get(base) ?? 0;
      seen.set(base, count + 1);
      out.push({
        level: match[1].length as 2 | 3,
        text,
        id: count === 0 ? base : `${base}-${count}`,
        line: block.start + offset,
      });
    });
  }
  return out;
};

/** *next* ending in exactly the blank lines *source* ended with (the editor adds its own). */
export const keepTrailing = (source: string, next: string): string =>
  next.replace(/\n+$/, "") + (source.match(/\n*$/)?.[0] ?? "");
