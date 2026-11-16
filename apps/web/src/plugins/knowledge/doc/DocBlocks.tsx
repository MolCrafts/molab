/**
 * The non-prose blocks of a knowledge page (L10): MkDocs admonitions (a left
 * rule and a washed title bar in the type's colour; `???` folds), content tabs
 * (an accent underline on the active tab) and the `<molab-…>` component slot.
 */

import {
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  CircleHelp,
  CircleX,
  FileText,
  FlaskConical,
  Info,
  Lightbulb,
  type LucideIcon,
  Pencil,
  Quote,
} from "lucide-react";
import { type JSX, type ReactNode, useState } from "react";
import { cn } from "@/lib/utils";
import { type AdmonitionBlock, type ComponentBlock, parseAttrs, type TabsBlock } from "./blocks";
import { DocMarkdown } from "./DocMarkdown";
import { ComponentNotice } from "./frame";
import { componentSpec } from "./registry";

const ADMONITION_ICON: Record<string, LucideIcon> = {
  note: Pencil,
  abstract: FileText,
  summary: FileText,
  info: Info,
  tip: Lightbulb,
  hint: Lightbulb,
  success: CircleCheck,
  check: CircleCheck,
  done: CircleCheck,
  question: CircleHelp,
  warning: CircleAlert,
  caution: CircleAlert,
  attention: CircleAlert,
  failure: CircleX,
  fail: CircleX,
  danger: CircleX,
  error: CircleX,
  bug: CircleX,
  example: FlaskConical,
  quote: Quote,
  cite: Quote,
};

const titleCase = (word: string): string => word.charAt(0).toUpperCase() + word.slice(1);

/** Prose inside an admonition or a tab: markdown, read-only boxes. */
const NestedMarkdown = ({ text }: { text: string }): JSX.Element => (
  <DocMarkdown text={text} startLine={0} headingIds={[]} />
);

export const AdmonitionView = ({ block }: { block: AdmonitionBlock }): JSX.Element => {
  const [open, setOpen] = useState(block.fold !== "closed");
  const Icon = ADMONITION_ICON[block.type] ?? Pencil;
  const title = block.title ?? titleCase(block.type);
  const folds = block.fold !== "none";
  const Chevron = open ? ChevronDown : ChevronRight;
  const head: ReactNode = (
    <>
      <Icon aria-hidden className="size-icon-sm flex-none text-[color:var(--adm)]" />
      <span className="flex-1 font-semibold">{title}</span>
      {folds ? <Chevron aria-hidden className="size-icon-sm text-muted-foreground" /> : null}
    </>
  );
  return (
    <aside
      data-type={block.type}
      className="doc-admonition my-4 overflow-hidden rounded-control bg-surface"
    >
      {folds ? (
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="doc-admonition-title flex h-8 w-full items-center gap-2 px-3 text-left text-body-lg"
        >
          {head}
        </button>
      ) : (
        <div className="doc-admonition-title flex h-8 items-center gap-2 px-3 text-body-lg">
          {head}
        </div>
      )}
      {open && block.body ? (
        <div className="px-4 py-1 [&_p]:my-2">
          <NestedMarkdown text={block.body} />
        </div>
      ) : null}
    </aside>
  );
};

export const TabsView = ({ block }: { block: TabsBlock }): JSX.Element => {
  const [active, setActive] = useState(0);
  const current = block.tabs[active] ?? block.tabs[0];
  return (
    <div className="my-4">
      <div role="tablist" className="flex gap-4 border-b border-border">
        {block.tabs.map((tab, index) => (
          <button
            key={tab.label}
            type="button"
            role="tab"
            aria-selected={index === active}
            onClick={() => setActive(index)}
            className={cn(
              "h-8 text-body",
              index === active
                ? "font-semibold text-doc-accent shadow-[inset_0_-2px_0_var(--doc-accent)]"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="pt-2">
        {current ? <NestedTabBody body={current.body} /> : null}
      </div>
    </div>
  );
};

/** A tab body may itself hold one component line (`=== "Chart"` + `::molab-metric-chart`). */
const NestedTabBody = ({ body }: { body: string }): JSX.Element => {
  const single = body.trim().match(/^::(molab-[a-z][a-z0-9-]*)(?:\{(.*)\})?$/);
  if (single?.[1]) {
    return <ComponentView name={single[1]} attrsText={single[2] ?? ""} />;
  }
  return <NestedMarkdown text={body} />;
};

const ComponentView = ({ name, attrsText }: { name: string; attrsText: string }): JSX.Element => {
  const spec = componentSpec(name);
  if (!spec)
    return <ComponentNotice name={name}>is not a component this version knows.</ComponentNotice>;
  const attrs = parseAttrs(attrsText);
  const { Component } = spec;
  return <Component attrs={attrs} />;
};

export const ComponentBlockView = ({ block }: { block: ComponentBlock }): JSX.Element => {
  const spec = componentSpec(block.name);
  if (!spec) {
    return (
      <ComponentNotice name={block.name}>is not a component this version knows.</ComponentNotice>
    );
  }
  const { Component } = spec;
  return (
    <div className="my-4">
      <Component attrs={block.attrs} />
    </div>
  );
};
