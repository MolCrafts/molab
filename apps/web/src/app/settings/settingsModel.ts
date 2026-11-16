/**
 * Settings (L11): categories in the side bar, one category per page, and a
 * search across every category. A category's page is a list of entries; an
 * entry is one setting (`SettingItem`), its title and description are what
 * search reads.
 */

import { Cpu, History, type LucideIcon, Palette, Puzzle, Server, Users } from "lucide-react";
import type { ReactNode } from "react";

export const SETTINGS_ROOT = "/settings";

export interface SettingsCategoryMeta {
  id: string;
  label: string;
  icon: LucideIcon;
  description?: string;
}

/** The built-in categories, in side-bar order. */
export const SETTINGS_CATEGORIES: readonly SettingsCategoryMeta[] = [
  { id: "appearance", label: "Appearance", icon: Palette },
  {
    id: "remote-workspaces",
    label: "Remote workspaces",
    icon: Server,
    description:
      "Workspaces molab serves from another machine. The active one is what the workbench shows.",
  },
  {
    id: "compute-targets",
    label: "Compute targets",
    icon: Cpu,
    description: "Where runs execute. A run names its target.",
  },
  {
    id: "history",
    label: "History",
    icon: History,
    description: "Every fact molab records is a commit in the workspace’s git log.",
  },
  {
    id: "plugins",
    label: "Plugins",
    icon: Puzzle,
    description: "Turn a plugin off to hide what it adds.",
  },
  {
    id: "users",
    label: "Users",
    icon: Users,
    description: "Accounts for this serve process, under ~/.molab/auth/.",
  },
];

export const DEFAULT_CATEGORY = "appearance";

/** One setting on a category page. */
export interface SettingEntry {
  id: string;
  /** Plain text, for search. */
  title: string;
  description?: string;
  /** Extra words search should find it by (an entry's path, a plugin id). */
  keywords?: readonly string[];
  /** The setting itself; a search page passes the category name. */
  render: (category?: string) => ReactNode;
}

/** `/settings/<id>`; old `/settings` and unknown ids read as the default. */
export const settingsPath = (categoryId: string): string =>
  `${SETTINGS_ROOT}/${encodeURIComponent(categoryId)}`;

export const categoryFromPath = (pathname: string, known: readonly string[]): string => {
  const rest = pathname.startsWith(`${SETTINGS_ROOT}/`)
    ? decodeURIComponent(pathname.slice(SETTINGS_ROOT.length + 1).split("/")[0] ?? "")
    : "";
  // The pre-L11 ids still land on their page.
  const legacy: Record<string, string> = { "ui-plugins": "plugins" };
  const id = legacy[rest] ?? rest;
  return known.includes(id) ? id : DEFAULT_CATEGORY;
};

/** Every word of the query appears in the entry's title, description or keywords. */
export const matchesQuery = (entry: SettingEntry, query: string, category = ""): boolean => {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return false;
  const haystack = [category, entry.title, entry.description ?? "", ...(entry.keywords ?? [])]
    .join(" ")
    .toLowerCase();
  return words.every((word) => haystack.includes(word));
};
