/**
 * Settings › Plugins (L11): each plugin is a setting — its name (Built in for
 * the ones that cannot be turned off), its description, and under it the
 * switch and what it adds, read from the contribution registries.
 * Preferences persist in localStorage.
 */

import { Switch } from "@molcrafts/ui";
import type { JSX } from "react";
import { SettingItem, SettingTag } from "@/components/settings";
import { describePluginContributions, useContributionGeneration } from "@/lib/contribution-runtime";
import { listPluginCatalog, type PluginCatalogEntry } from "@/plugins/catalog";
import {
  isPluginEnabled,
  setPluginEnabled,
  usePluginPreferencesGeneration,
} from "@/plugins/preferences";
import { ensureInternalPlugin } from "@/plugins/runtime";
import type { SettingEntry } from "./settingsModel";

const PluginSetting = ({
  plugin,
  category,
}: {
  plugin: PluginCatalogEntry;
  category?: string;
}): JSX.Element => {
  usePluginPreferencesGeneration();
  useContributionGeneration();
  const enabled = isPluginEnabled(plugin.id);
  const adds = describePluginContributions(plugin.id);
  const switchId = `plugin-${plugin.id}`;
  return (
    <SettingItem
      id={switchId}
      category={category}
      title={plugin.name}
      tag={plugin.userToggleable ? null : <SettingTag>Built in</SettingTag>}
      description={plugin.description}
    >
      <div className="flex items-center gap-3">
        {plugin.userToggleable ? (
          <Switch
            id={switchId}
            checked={enabled}
            onCheckedChange={(checked) => {
              setPluginEnabled(plugin.id, checked);
              if (checked) void ensureInternalPlugin(plugin.id);
            }}
            aria-label={`${enabled ? "Turn off" : "Turn on"} ${plugin.name}`}
          />
        ) : null}
        {adds.length ? (
          <span className="text-label text-muted-foreground">Adds {adds.join(" · ")}</span>
        ) : null}
      </div>
    </SettingItem>
  );
};

/** Every plugin the app knows, built-in ones included. */
export const usePluginEntries = (): SettingEntry[] => {
  usePluginPreferencesGeneration();
  return listPluginCatalog().map((plugin) => ({
    id: `plugin:${plugin.id}`,
    title: plugin.name,
    description: plugin.description,
    keywords: [plugin.id, "plugin"],
    render: (category) => <PluginSetting key={plugin.id} plugin={plugin} category={category} />,
  }));
};
