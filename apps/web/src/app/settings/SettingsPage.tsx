/**
 * Settings (L11): the editor shows one category — `/settings/<id>` — as a
 * stack of settings, or, while the side bar's search has text (`?q=`), every
 * matching setting as "Category › Setting". The categories and the search
 * field live in the side bar (`SettingsExplorer`).
 */

import type { JSX } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { SettingsPageHeader } from "@/components/settings";
import { categoryFromPath, matchesQuery } from "./settingsModel";
import { useSettingsCategories } from "./useSettingsCategories";

export const SETTINGS_QUERY_PARAM = "q";

export function SettingsPage(): JSX.Element {
  const categories = useSettingsCategories();
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const query = (params.get(SETTINGS_QUERY_PARAM) ?? "").trim();

  if (query) {
    const matches = categories.flatMap((category) =>
      category.entries
        .filter((entry) => matchesQuery(entry, query, category.label))
        .map((entry) => ({ category, entry })),
    );
    return (
      <section aria-label="Search settings" className="h-full min-h-0 overflow-auto bg-background">
        <div className="flex max-w-3xl flex-col px-6 pt-2 pb-8 max-md:px-4">
          <p className="py-2 text-label text-muted-foreground">
            {matches.length === 0
              ? `No setting matches “${query}”.`
              : `${matches.length} ${matches.length === 1 ? "setting matches" : "settings match"} “${query}”`}
          </p>
          {matches.map(({ category, entry }) => entry.render(category.label))}
        </div>
      </section>
    );
  }

  const id = categoryFromPath(
    pathname,
    categories.map((category) => category.id),
  );
  const category = categories.find((item) => item.id === id) ?? categories[0];
  if (!category) return <div />;
  return (
    <section aria-label={category.label} className="h-full min-h-0 overflow-auto bg-background">
      <div className="flex max-w-3xl flex-col px-6 pt-2 pb-8 max-md:px-4">
        <SettingsPageHeader title={category.label} description={category.description} />
        {category.entries.map((entry) => entry.render())}
      </div>
    </section>
  );
}
