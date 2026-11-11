/**
 * Settings in the side bar (L11): a search field over every setting, then the
 * categories with their counts. Picking a category opens its page; typing
 * replaces the page with the matches (`?q=`).
 */

import { Input } from "@molcrafts/ui";
import { Search } from "lucide-react";
import type { JSX } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { type TreeNode, TreeView } from "@/app/panels/TreeView";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { SETTINGS_QUERY_PARAM } from "./SettingsPage";
import { categoryFromPath, SETTINGS_ROOT, settingsPath } from "./settingsModel";
import { useSettingsNav } from "./useSettingsCategories";

export const SettingsExplorer = (): JSX.Element => {
  const nav = useSettingsNav();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [params, setParams] = useSearchParams();
  const query = params.get(SETTINGS_QUERY_PARAM) ?? "";
  const active = query
    ? null
    : categoryFromPath(
        pathname,
        nav.map((item) => item.id),
      );

  const nodes: TreeNode[] = nav.map((item) => ({
    id: item.id,
    label: item.label,
    icon: item.icon,
    iconClassName: "text-muted-foreground",
    meta: item.count != null ? String(item.count) : undefined,
    onSelect: () => navigate(settingsPath(item.id)),
  }));

  const search = (
    <div className="relative flex w-full flex-none items-center px-3 pb-2">
      <Search
        aria-hidden
        className="pointer-events-none absolute left-6 size-icon-sm text-muted-foreground"
      />
      <Input
        type="search"
        value={query}
        aria-label="Search settings"
        placeholder="Search settings"
        className="h-control-compact pl-8"
        onChange={(event) => {
          const value = event.target.value;
          if (!pathname.startsWith(SETTINGS_ROOT)) navigate(SETTINGS_ROOT);
          setParams(value ? { [SETTINGS_QUERY_PARAM]: value } : {}, { replace: true });
        }}
      />
    </div>
  );

  return (
    <LeftExplorer title="Settings">
      {search}
      <TreeView nodes={nodes} activeId={active ?? undefined} emptyTitle="No settings" />
    </LeftExplorer>
  );
};
