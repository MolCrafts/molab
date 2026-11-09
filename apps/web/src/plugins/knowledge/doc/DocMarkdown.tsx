/**
 * One markdown block of a knowledge page (L10), in the MkDocs reading style:
 * h2 22px regular with ¶ on hover, h3 16px semibold, body 15px, accent list
 * bullets, GFM task boxes that toggle their line, `molab:` links as chips,
 * document-relative images as captioned figures.
 *
 * Heading ids and task lines are matched by order within the block (the math
 * normaliser can shift line numbers, so positions are not used). It calls
 * react-markdown itself, with the shared math normaliser: the shared renderer
 * styles headings for panels, and its descendant rules would win here.
 */

import { Check } from "lucide-react";
import type { JSX, ReactNode } from "react";
import "katex/dist/katex.min.css";
import { prepareMarkdownMath } from "@molcrafts/ui-markdown";
import ReactMarkdown, { type Components, defaultUrlTransform } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { isMolabRef } from "@/lib/molab-ref";
import { cn } from "@/lib/utils";
import { proxyKnowledgeImageUrl } from "../knowledgeMedia";
import { useOptionalDoc } from "./context";
import { RefChip } from "./RefChip";

const FENCE = /^ {0,3}(`{3,}|~{3,})/;
const TASK = /^\s*[-*+]\s+\[[ xX]\]\s/;

/** Body-relative line numbers of the GFM task items in *text*, in order. */
export const taskLines = (text: string): number[] => {
  const out: number[] = [];
  let fence: string | null = null;
  text.split("\n").forEach((line, index) => {
    const marker = line.match(FENCE);
    if (fence !== null) {
      if (marker?.[1] && marker[1][0] === fence[0]) fence = null;
      return;
    }
    if (marker?.[1]) {
      fence = marker[1];
      return;
    }
    if (TASK.test(line)) out.push(index);
  });
  return out;
};

/** `<molab-markdown>` / `</molab-markdown>` lines wrap prose in an HTML document; they draw nothing. */
const stripWrapper = (text: string): string => text.replace(/^\s*<\/?molab-markdown\s*>\s*$/gm, "");

const Anchor = ({ id }: { id: string }): JSX.Element => (
  <a
    href={`#${id}`}
    aria-label="Link to this section"
    className="ml-2 text-muted-foreground no-underline opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
  >
    ¶
  </a>
);

const TaskBox = ({
  checked,
  onToggle,
}: {
  checked: boolean;
  onToggle: (() => void) | null;
}): JSX.Element => (
  <span className="relative mr-2 inline-flex size-4 translate-y-0.5 align-baseline">
    <input
      type="checkbox"
      checked={checked}
      aria-label={checked ? "Mark not done" : "Mark done"}
      disabled={!onToggle}
      onChange={onToggle ?? undefined}
      className={cn(
        "peer size-4 appearance-none rounded-sm border",
        checked ? "border-status-completed bg-status-completed" : "border-input bg-surface",
        onToggle ? "cursor-pointer" : "cursor-default",
      )}
    />
    {checked ? (
      <Check
        aria-hidden
        className="pointer-events-none absolute inset-0 m-auto size-3 text-accent-foreground"
        strokeWidth={3}
      />
    ) : null}
  </span>
);

export interface DocMarkdownProps {
  text: string;
  /** Source line of the block's first line, to map task boxes back. */
  startLine: number;
  /** Anchor ids of this block's h2/h3, in order. */
  headingIds: readonly string[];
  /** Flip the task box on an absolute source line; absent = read-only. */
  onToggleTask?: (line: number) => void;
}

export const DocMarkdown = ({
  text,
  startLine,
  headingIds,
  onToggleTask,
}: DocMarkdownProps): JSX.Element => {
  const doc = useOptionalDoc();
  const clean = stripWrapper(text);
  const tasks = taskLines(text);
  let heading = 0;
  let task = 0;
  const nextHeadingId = (): string | undefined => headingIds[heading++];

  const components: Components = {
    h1: ({ children }) => <h2 className="mt-6 mb-2 text-doc-h2 font-normal">{children}</h2>,
    h2: ({ children }) => {
      const id = nextHeadingId();
      return (
        <h2 id={id} className="group mt-8 mb-3 scroll-mt-6 text-doc-h2 font-normal first:mt-0">
          {children}
          {id ? <Anchor id={id} /> : null}
        </h2>
      );
    },
    h3: ({ children }) => {
      const id = nextHeadingId();
      return (
        <h3 id={id} className="group mt-6 mb-2 scroll-mt-6 text-doc-h3 font-semibold">
          {children}
          {id ? <Anchor id={id} /> : null}
        </h3>
      );
    },
    h4: ({ children }) => <h4 className="mt-4 mb-1 text-doc font-semibold">{children}</h4>,
    p: ({ children }) => <p className="my-3 text-doc">{children}</p>,
    ul: ({ children, className }) => (
      <ul
        className={cn(
          "my-3 space-y-1 pl-6 text-doc",
          className?.includes("contains-task-list")
            ? "list-none pl-0"
            : "list-disc marker:text-doc-accent",
        )}
      >
        {children}
      </ul>
    ),
    ol: ({ children }) => (
      <ol className="my-3 list-decimal space-y-1 pl-6 text-doc marker:text-doc-accent">
        {children}
      </ol>
    ),
    li: ({ children }) => <li className="pl-1">{children}</li>,
    input: ({ checked, type }) => {
      if (type !== "checkbox") return null;
      const line = tasks[task++];
      const toggle =
        onToggleTask && line !== undefined ? () => onToggleTask(startLine + line) : null;
      return <TaskBox checked={Boolean(checked)} onToggle={toggle} />;
    },
    blockquote: ({ children }) => (
      <blockquote className="my-4 border-l-4 border-border pl-4 text-doc text-muted-foreground">
        {children}
      </blockquote>
    ),
    hr: () => <hr className="my-6 border-border" />,
    code: ({ children, className }) =>
      className ? (
        <code className={cn("font-mono text-body", className)}>{children}</code>
      ) : (
        <code className="rounded-sm bg-surface-subtle px-1 font-mono text-body">{children}</code>
      ),
    pre: ({ children }) => (
      <pre className="my-4 overflow-x-auto rounded-control border border-border bg-surface p-3 font-mono text-body">
        {children}
      </pre>
    ),
    table: ({ children }) => (
      <div className="my-4 overflow-x-auto rounded-control border border-border bg-surface">
        <table className="w-full border-collapse text-body">{children}</table>
      </div>
    ),
    th: ({ children }) => (
      <th className="h-7 border-b border-border px-3 text-left font-normal text-muted-foreground">
        {children}
      </th>
    ),
    td: ({ children }) => <td className="h-6 border-t border-border px-3">{children}</td>,
    a: ({ href, children }) =>
      isMolabRef(href) ? (
        <RefChip refText={href}>{children as ReactNode}</RefChip>
      ) : (
        <a
          href={href}
          target={href?.startsWith("/") || href?.startsWith("#") ? undefined : "_blank"}
          rel="noreferrer"
          className="text-link underline-offset-2 hover:underline"
        >
          {children}
        </a>
      ),
    img: ({ src, alt }) => {
      const url = typeof src === "string" && doc ? proxyKnowledgeImageUrl(doc.relPath, src) : src;
      return (
        <figure className="my-4 overflow-hidden rounded-control border border-border bg-surface">
          <img
            src={typeof url === "string" ? url : undefined}
            alt={alt ?? ""}
            className="block max-w-full"
          />
          {alt ? (
            <figcaption className="border-t border-border px-3 py-1 text-label text-muted-foreground">
              {alt}
            </figcaption>
          ) : null}
        </figure>
      );
    },
  };

  // The page owns its type: the shared renderer styles headings for panels, not pages.
  return (
    <div className="doc-markdown leading-relaxed [overflow-wrap:anywhere]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { strict: "ignore" }]]}
        urlTransform={(url) => (isMolabRef(url) ? url : defaultUrlTransform(url))}
        components={components}
      >
        {prepareMarkdownMath(clean)}
      </ReactMarkdown>
    </div>
  );
};
