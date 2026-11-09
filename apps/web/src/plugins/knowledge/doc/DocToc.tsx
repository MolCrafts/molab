/**
 * "On this page" (L10): the page's h2 / h3, h3 indented; the section in view
 * is drawn in the class accent with an accent rule. On a narrow page it folds
 * into a disclosure under the title.
 */

import { ChevronDown, ChevronRight, ListTree } from "lucide-react";
import { type JSX, type RefObject, useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import type { DocHeading } from "./blocks";

/** The id of the last heading scrolled past the top of *root*. */
const useActiveHeading = (
  headings: readonly DocHeading[],
  root: RefObject<HTMLElement | null>,
): string | null => {
  const [active, setActive] = useState<string | null>(headings[0]?.id ?? null);
  useEffect(() => {
    const container = root.current;
    if (!container || headings.length === 0) return;
    const onScroll = (): void => {
      const top = container.getBoundingClientRect().top + 24;
      let current = headings[0]?.id ?? null;
      for (const heading of headings) {
        const el = container.querySelector(`#${CSS.escape(heading.id)}`);
        if (el && el.getBoundingClientRect().top <= top) current = heading.id;
      }
      setActive(current);
    };
    onScroll();
    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
  }, [headings, root]);
  return active;
};

const TocLinks = ({
  headings,
  active,
}: {
  headings: readonly DocHeading[];
  active: string | null;
}): JSX.Element => (
  <ul className="flex flex-col">
    {headings.map((heading) => (
      <li key={heading.id}>
        <a
          href={`#${heading.id}`}
          className={cn(
            "block border-l-2 py-1 text-body no-underline",
            heading.level === 3 ? "pl-6" : "pl-3",
            heading.id === active
              ? "border-doc-accent font-medium text-doc-accent"
              : "border-border text-muted-foreground hover:text-foreground",
          )}
        >
          {heading.text}
        </a>
      </li>
    ))}
  </ul>
);

export const DocToc = ({
  headings,
  scrollRoot,
}: {
  headings: readonly DocHeading[];
  scrollRoot: RefObject<HTMLElement | null>;
}): JSX.Element | null => {
  const active = useActiveHeading(headings, scrollRoot);
  if (headings.length === 0) return null;
  return (
    <nav aria-label="On this page" className="sticky top-6 w-doc-toc flex-none pt-2">
      <p className="pb-2 pl-3 text-label font-semibold text-muted-foreground">On this page</p>
      <TocLinks headings={headings} active={active} />
    </nav>
  );
};

/** The narrow-page form: a disclosure under the title. */
export const DocTocDisclosure = ({
  headings,
}: {
  headings: readonly DocHeading[];
}): JSX.Element | null => {
  const [open, setOpen] = useState(false);
  if (headings.length < 2) return null;
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div className="mb-4 rounded-control border border-border bg-surface">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex h-8 w-full items-center gap-2 px-3 text-body"
      >
        <ListTree aria-hidden className="size-icon-sm text-muted-foreground" />
        <span className="flex-1 text-left">On this page</span>
        <Chevron aria-hidden className="size-icon-sm text-muted-foreground" />
      </button>
      {open ? (
        <div className="border-t border-border py-2 pr-3">
          <TocLinks headings={headings} active={null} />
        </div>
      ) : null}
    </div>
  );
};
