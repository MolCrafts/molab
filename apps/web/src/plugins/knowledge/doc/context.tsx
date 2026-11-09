/**
 * What a `<molab-…>` component may know about the document it sits in (L10).
 * The page provides it; components read it with `useDoc()`.
 */

import type { LucideIcon } from "lucide-react";
import { type ComponentType, createContext, useContext } from "react";
import type { EntityCard } from "@/api/generated/models/EntityCard";
import type { RendererSnapshot } from "@/app/types";
import type { MolabRefTarget } from "@/lib/molab-ref";
import type { KnowledgeClass } from "../knowledgeClass";

export interface DocContextValue {
  /** Workspace-relative path of the document (its identity). */
  relPath: string;
  cls: KnowledgeClass;
  /** Workspace-relative host directory ("" = workspace root). */
  hostPath: string;
  /** The class record (Todo items, Roadmap stages, Milestone, Delegation …); `{}` when none. */
  record: Record<string, unknown>;
  /** Entities the document links to, resolved by the server. */
  cards: readonly EntityCard[];
  snapshot: RendererSnapshot;
  refIndex: ReadonlyMap<string, MolabRefTarget>;
  /** Replace the class record (PATCH). Rejects with a readable message. */
  saveRecord: (record: Record<string, unknown>) => Promise<void>;
  /**
   * Change the body. `save: true` writes at once (a checkbox click);
   * otherwise the edit joins the unsaved draft (● and ⌘S).
   */
  changeBody: (update: (body: string) => string, options?: { save?: boolean }) => void;
  /** Whether the reader may change the document (false for a read-only host). */
  writable: boolean;
}

const DocContext = createContext<DocContextValue | null>(null);

export const DocContextProvider = DocContext.Provider;

/** The document a component is rendered in. Throws outside a document page. */
export const useDoc = (): DocContextValue => {
  const value = useContext(DocContext);
  if (!value) throw new Error("useDoc() is only available inside a knowledge document page.");
  return value;
};

/** The same, or null outside a page (a component previewed on its own). */
export const useOptionalDoc = (): DocContextValue | null => useContext(DocContext);

export interface DocComponentProps {
  /** The element's attributes, as written (`::molab-x{a=1}` or `<molab-x a="1">`). */
  attrs: Readonly<Record<string, string>>;
}

/** One `<molab-…>` component: how "/" offers it and how the page draws it. */
export interface DocComponentSpec {
  /** Element name, e.g. `molab-run-table`. */
  name: `molab-${string}`;
  /** "/" menu label (a noun: "Run table"). */
  label: string;
  /** One line for the "/" menu. */
  description: string;
  keywords: readonly string[];
  icon: LucideIcon;
  /** Attributes a fresh insert starts with (may be empty). */
  template: Readonly<Record<string, string>>;
  Component: ComponentType<DocComponentProps>;
}
