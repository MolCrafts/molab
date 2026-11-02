import type { JSX } from "react";
import ReactMarkdown, { type Components, defaultUrlTransform } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

/**
 * Stand-in for `@molcrafts/ui-markdown`. That package is declared as a
 * sibling checkout (`molcrafts-ui/packages/markdown`) which this tree does
 * not contain, and it is not published. The math functions follow the
 * contract in `src/lib/markdown-math.test.ts`.
 */

const fenceOpen = /^ {0,3}(`{3,}|~{3,})/;

/** Leave fenced code blocks untouched. The fence marker itself is kept. */
function mapOutsideFences(src: string, mapLine: (line: string) => string): string {
  const lines = src.split("\n");
  let fence: string | null = null;
  const out = lines.map((line) => {
    const marker = line.match(fenceOpen);
    if (fence !== null) {
      if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length) {
        const rest = line.slice(line.indexOf(marker[1]) + marker[1].length);
        if (rest.trim() === "") fence = null;
      }
      return line;
    }
    if (marker) {
      fence = marker[1];
      return line;
    }
    return mapLine(line);
  });
  return out.join("\n");
}

/** `\(...\)` becomes `$...$`. `\[...\]` becomes a fenced display block. */
export function normalizeLatexDelimiters(src: string): string {
  return mapOutsideFences(src, (line) =>
    line
      .replace(/\\\((.+?)\\\)/g, (_match, body: string) => `$${body}$`)
      .replace(/\\\[(.+?)\\\]/g, (_match, body: string) => `$$\n${body}\n$$`),
  );
}

/**
 * A whole line that is one `$$...$$` formula becomes a fenced display block.
 * Mid-line formulas, two formulas on one line, and empty fences stay as written.
 */
export function normalizeDisplayMath(src: string): string {
  return mapOutsideFences(src, (line) => {
    const match = line.match(/^(\s*)\$\$(\s*\S.*?)\s*\$\$\s*$/);
    if (!match) return line;
    const indent = match[1] ?? "";
    const body = match[2]?.trim() ?? "";
    if (body === "" || body.includes("$$")) return line;
    return `${indent}$$\n${indent}${body}\n${indent}$$`;
  });
}

export function prepareMarkdownMath(src: string): string {
  return normalizeDisplayMath(normalizeLatexDelimiters(src));
}

type UrlTransform = (url: string) => string | undefined;

export function MarkdownContent({
  text,
  className,
  urlTransform,
  components,
}: {
  text: string;
  className?: string;
  urlTransform?: UrlTransform;
  components?: Components;
}): JSX.Element {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { strict: "ignore" }]]}
        urlTransform={(url) => {
          const next = urlTransform?.(url);
          return next === undefined ? defaultUrlTransform(url) : next;
        }}
        components={components}
      >
        {prepareMarkdownMath(text)}
      </ReactMarkdown>
    </div>
  );
}
