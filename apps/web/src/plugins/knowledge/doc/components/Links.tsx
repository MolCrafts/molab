/**
 * `<molab-links>` (L10, Figma v4_01): what the document links to ("Linked":
 * the entities the server resolved) and what links to it ("Linked from":
 * backlinks). Computed, never typed. `LinksSections` is the bare pair the page
 * appends under every document, headed as the page's h2s; an empty section
 * draws nothing.
 */

import {
  Archive,
  Blocks,
  FileText,
  FlaskConical,
  Link2,
  type LucideIcon,
  PlayCircle,
} from "lucide-react";
import type { JSX, ReactNode } from "react";
import type { EntityCard } from "@/api/generated/models/EntityCard";
import type { NoteSummary } from "@/api/generated/models/NoteSummary";
import { StatusIcon } from "@/app/components/entity";
import { usePreview } from "@/app/preview/PreviewContext";
import type { PreviewTarget } from "@/app/preview/target";
import { useNavigationState } from "@/app/state/useNavigationState";
import { cn } from "@/lib/utils";
import { knowledgeClassOf } from "../../knowledgeClass";
import { knowledgeClassIcon } from "../../knowledgeClassIcon";
import { useKnowledgeBacklinksQuery } from "../../queries";
import { type DocComponentProps, type DocComponentSpec, useDoc } from "../context";
import { ComponentLoading, ComponentNotice } from "../frame";
import { resolveDocRef } from "../RefChip";

const NAME = "molab-links";

const KIND_ICON: Record<string, LucideIcon> = {
  run: PlayCircle,
  experiment: FlaskConical,
  project: Blocks,
  asset: Archive,
};

const rowClass =
  "flex h-7 w-full min-w-0 items-center gap-2 rounded-control px-1 text-left text-body outline-none focus-visible:ring-2 focus-visible:ring-ring";

type Heading = "page" | "block";

/** `page`: the document's h2 (appended under every page); `block`: 13px title on a hairline. */
const Section = ({
  title,
  heading,
  children,
}: {
  title: string;
  heading: Heading;
  children: ReactNode;
}): JSX.Element => (
  <section aria-label={title}>
    {heading === "page" ? (
      <h2 className="mt-8 mb-3 text-doc-h2 font-normal text-foreground">{title}</h2>
    ) : (
      <h3 className="mb-1 flex items-center gap-3 text-body font-semibold text-foreground">
        {title}
        <span aria-hidden className="h-px flex-1 bg-border" />
      </h3>
    )}
    <ul>{children}</ul>
  </section>
);

const RowText = ({ name, kind }: { name: string; kind: string }): JSX.Element => (
  <>
    <span className="truncate text-foreground">{name}</span>
    <span className="flex-none truncate text-label text-muted-foreground">{kind}</span>
    <span className="flex-1" />
  </>
);

const LinkedRow = ({ card }: { card: EntityCard }): JSX.Element => {
  const doc = useDoc();
  const preview = usePreview();
  const hit = card.ref ? resolveDocRef(card.ref, doc.refIndex, doc.snapshot) : null;
  const target: PreviewTarget | null = card.missing
    ? null
    : (hit?.target ??
      (card.relPath && !KIND_ICON[card.kind] ? { kind: "knowledge", path: card.relPath } : null));
  const Icon = KIND_ICON[card.kind] ?? FileText;
  const status = card.status ?? hit?.status ?? null;
  return (
    <li>
      <button
        type="button"
        disabled={!target}
        title={card.ref ?? card.relPath ?? card.title}
        onClick={() => target && preview.preview(target)}
        onDoubleClick={() => target && preview.open(target)}
        className={cn(rowClass, target ? "hover:bg-surface-subtle" : "cursor-default opacity-60")}
      >
        <Icon aria-hidden className="size-icon-sm flex-none text-muted-foreground" />
        <RowText name={card.title} kind={card.kind} />
        {status ? <StatusIcon status={status} /> : null}
      </button>
    </li>
  );
};

const BacklinkRow = ({
  note,
  onOpen,
}: {
  note: NoteSummary;
  onOpen: (relPath: string) => void;
}): JSX.Element => {
  const ClassIcon = knowledgeClassIcon(knowledgeClassOf(note));
  return (
    <li>
      <button
        type="button"
        title={note.hostPath ? `${note.hostPath} · ${note.relPath}` : note.relPath}
        onClick={() => onOpen(note.relPath)}
        className={cn(rowClass, "hover:bg-surface-subtle")}
      >
        <ClassIcon aria-hidden className="size-icon-sm flex-none text-muted-foreground" />
        <RowText name={note.name} kind={knowledgeClassOf(note).toLowerCase()} />
      </button>
    </li>
  );
};

/** The document's links both ways, from the page context and the backlinks query. */
const useDocLinks = () => {
  const doc = useDoc();
  const backlinks = useKnowledgeBacklinksQuery(doc.relPath);
  return {
    cards: doc.cards,
    backlinks: backlinks.data?.backlinks ?? [],
    pending: backlinks.isPending,
  };
};

const Sections = ({
  cards,
  backlinks,
  heading,
}: {
  cards: readonly EntityCard[];
  backlinks: readonly NoteSummary[];
  heading: Heading;
}): JSX.Element => {
  const doc = useDoc();
  const nav = useNavigationState(doc.snapshot);
  const openDoc = (relPath: string): void =>
    nav.setSelection({ objectType: "knowledge", objectId: relPath });
  return (
    <div className={cn("not-prose", heading === "block" && "space-y-6")}>
      {cards.length > 0 ? (
        <Section title="Linked" heading={heading}>
          {cards.map((card) => (
            <LinkedRow key={`${card.kind}:${card.id}`} card={card} />
          ))}
        </Section>
      ) : null}
      {backlinks.length > 0 ? (
        <Section title="Linked from" heading={heading}>
          {backlinks.map((note) => (
            <BacklinkRow key={note.relPath} note={note} onOpen={openDoc} />
          ))}
        </Section>
      ) : null}
    </div>
  );
};

/** Linked / Linked from under a document; nothing when neither has a row. */
export const LinksSections = (): JSX.Element | null => {
  const { cards, backlinks } = useDocLinks();
  if (cards.length === 0 && backlinks.length === 0) return null;
  return <Sections cards={cards} backlinks={backlinks} heading="page" />;
};

export const Links = (_props: DocComponentProps): JSX.Element => {
  const { cards, backlinks, pending } = useDocLinks();
  if (pending && cards.length === 0) return <ComponentLoading name={NAME} />;
  if (cards.length === 0 && backlinks.length === 0) {
    return (
      <ComponentNotice name={NAME}>Nothing links here, and this links to nothing.</ComponentNotice>
    );
  }
  return <Sections cards={cards} backlinks={backlinks} heading="block" />;
};

export const linksSpec: DocComponentSpec = {
  name: NAME,
  label: "Links",
  description: "Linked and Linked from, computed from the document.",
  keywords: ["links", "backlinks", "linked", "references"],
  icon: Link2,
  template: {},
  Component: Links,
};
