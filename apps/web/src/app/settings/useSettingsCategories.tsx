/**
 * The settings categories with their entries (the page), and with counts
 * only (the side bar). Plugin-contributed sections are categories of their
 * own, after the built-in ones.
 */

import { Puzzle } from "lucide-react";
import { useAuth } from "@/app/auth";
import { HISTORY_ENTRIES } from "@/app/history/HistoryPanel";
import { SettingItem } from "@/components/settings";
import { listPluginCatalog } from "@/plugins/catalog";
import { listSettingsSections, useWorkbenchGeneration } from "@/plugins/contributions/workbench";
import { APPEARANCE_ENTRIES } from "./AppearancePanel";
import { useComputeTargetEntries, useComputeTargets } from "./ComputeTargetsPanel";
import { useRemoteWorkspaceEntries, useRemoteWorkspaces } from "./RemoteWorkspacesPanel";
import { SETTINGS_CATEGORIES, type SettingEntry, type SettingsCategoryMeta } from "./settingsModel";
import { usePluginEntries } from "./UiPluginsPanel";
import { useUserEntries } from "./UsersSection";

export interface SettingsCategory extends SettingsCategoryMeta {
  entries: readonly SettingEntry[];
}

export interface SettingsNavItem extends SettingsCategoryMeta {
  count?: number;
}

const useShowsUsers = (): boolean => {
  const { enabled, user } = useAuth();
  return enabled && user?.role === "admin";
};

const pluginSectionCategories = (): SettingsCategory[] =>
  listSettingsSections().map((section) => {
    const Render = section.render;
    return {
      id: section.id,
      label: section.title,
      icon: Puzzle,
      entries: [
        {
          id: section.id,
          title: section.title,
          render: (category) => (
            <SettingItem key={section.id} id={section.id} category={category} title={section.title}>
              <Render />
            </SettingItem>
          ),
        },
      ],
    };
  });

const meta = (id: string): SettingsCategoryMeta => {
  const found = SETTINGS_CATEGORIES.find((category) => category.id === id);
  if (!found) throw new Error(`Unknown settings category ${id}`);
  return found;
};

/** Every category with its settings (the page and search). */
export const useSettingsCategories = (): SettingsCategory[] => {
  useWorkbenchGeneration();
  const showUsers = useShowsUsers();
  const remote = useRemoteWorkspaceEntries();
  const targets = useComputeTargetEntries();
  const plugins = usePluginEntries();
  const users = useUserEntries();
  return [
    { ...meta("appearance"), entries: APPEARANCE_ENTRIES },
    { ...meta("remote-workspaces"), entries: remote },
    { ...meta("compute-targets"), entries: targets },
    { ...meta("history"), entries: HISTORY_ENTRIES },
    { ...meta("plugins"), entries: plugins },
    ...(showUsers ? [{ ...meta("users"), entries: users }] : []),
    ...pluginSectionCategories(),
  ];
};

/** The side bar's categories and counts (no entry state). */
export const useSettingsNav = (): SettingsNavItem[] => {
  useWorkbenchGeneration();
  const showUsers = useShowsUsers();
  const remote = useRemoteWorkspaces();
  const targets = useComputeTargets();
  return [
    meta("appearance"),
    { ...meta("remote-workspaces"), count: remote.data?.length },
    { ...meta("compute-targets"), count: targets.data?.length },
    meta("history"),
    { ...meta("plugins"), count: listPluginCatalog().length },
    ...(showUsers ? [meta("users")] : []),
    ...pluginSectionCategories().map(({ entries: _entries, ...rest }) => rest),
  ];
};
