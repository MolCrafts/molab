/**
 * Workspace settings — molvis-style left nav + scroll sections.
 *
 * Sections: Appearance, Remote workspaces, Compute targets, UI plugins,
 * Users (admin when auth on). Chrome is domain-free
 * (`components/settings`); panels keep their own data.
 */

import { Cpu, Puzzle, Type, Users, Wifi } from "lucide-react";
import { useAuth } from "@/app/auth";
import { type SettingsNavEntry, SettingsSection, SettingsShell } from "@/components/settings";
import { listSettingsSections, useWorkbenchGeneration } from "@/plugins/contributions/workbench";
import { AppearancePanel } from "./AppearancePanel";
import { ComputeTargetsPanel } from "./ComputeTargetsPanel";
import { RemoteWorkspacesPanel } from "./RemoteWorkspacesPanel";
import { UiPluginsPanel } from "./UiPluginsPanel";
import { UsersSection } from "./UsersSection";

export function SettingsPage(): JSX.Element {
  const { enabled, user } = useAuth();
  const showUsers = enabled && user?.role === "admin";
  useWorkbenchGeneration();

  const entries: SettingsNavEntry[] = [
    {
      id: "appearance",
      label: "Appearance",
      group: "display",
      groupLabel: "Display",
      icon: <Type className="size-icon-sm" aria-hidden />,
      content: (
        <SettingsSection id="appearance" title="Appearance">
          <AppearancePanel />
        </SettingsSection>
      ),
    },
    {
      id: "remote-workspaces",
      label: "Remote workspaces",
      group: "workspace",
      groupLabel: "Workspace",
      icon: <Wifi className="size-icon-sm" aria-hidden />,
      content: (
        <SettingsSection id="remote-workspaces" title="Remote workspaces">
          <RemoteWorkspacesPanel />
        </SettingsSection>
      ),
    },
    {
      id: "compute-targets",
      label: "Compute targets",
      group: "workspace",
      groupLabel: "Workspace",
      icon: <Cpu className="size-icon-sm" aria-hidden />,
      content: (
        <SettingsSection id="compute-targets" title="Compute targets">
          <ComputeTargetsPanel />
        </SettingsSection>
      ),
    },
    {
      id: "ui-plugins",
      label: "UI plugins",
      group: "workspace",
      groupLabel: "Workspace",
      icon: <Puzzle className="size-icon-sm" aria-hidden />,
      content: (
        <SettingsSection id="ui-plugins" title="UI plugins">
          <UiPluginsPanel />
        </SettingsSection>
      ),
    },
    {
      id: "users",
      label: "Users",
      group: "access",
      groupLabel: "Access",
      icon: <Users className="size-icon-sm" aria-hidden />,
      hidden: !showUsers,
      content: <UsersSection sectionId="users" />,
    },
    ...listSettingsSections().map((section) => {
      const Render = section.render;
      return {
        id: section.id,
        label: section.title,
        group: section.group ?? "plugins",
        groupLabel: section.group ?? "Plugins",
        icon: <Puzzle className="size-icon-sm" aria-hidden />,
        content: (
          <SettingsSection id={section.id} title={section.title}>
            <Render />
          </SettingsSection>
        ),
      } satisfies SettingsNavEntry;
    }),
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <SettingsShell title="Settings" entries={entries} defaultId="appearance" className="h-full" />
    </div>
  );
}
