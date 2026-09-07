/**
 * Workbench contribution stores (commands, views, panels, status bar, settings).
 *
 * Existing renderer / file-type / execution registries stay in
 * `lib/contribution-runtime.ts`. This module owns the VS Code-shaped slots
 * that were missing as plugin APIs.
 */

import type {
  PluginPanelSpec,
  SettingsSectionSpec,
  StatusBarItemSpec,
  ViewContainerSpec,
  ViewSpec,
} from "@molcrafts/molexp-plugin";
import { useSyncExternalStore } from "react";
import { isPluginEnabled } from "@/lib/plugin-preferences";
import { ContributionStore } from "./store";

export interface CommandContribution {
  id: string;
  pluginId: string;
  title: string;
  category?: string;
  keybinding?: string;
  isVisible?: () => boolean;
  run: (args?: unknown) => unknown | Promise<unknown>;
}

export interface ViewContainerContribution extends ViewContainerSpec {
  pluginId: string;
}

export interface ViewContribution extends ViewSpec {
  pluginId: string;
}

export interface PanelContribution extends PluginPanelSpec {
  pluginId: string;
}

export interface StatusBarContribution extends StatusBarItemSpec {
  pluginId: string;
}

export interface SettingsSectionContribution extends SettingsSectionSpec {
  pluginId: string;
}

const commandStore = new ContributionStore<CommandContribution>();
const viewContainerStore = new ContributionStore<ViewContainerContribution>();
const viewStore = new ContributionStore<ViewContribution>();
const panelStore = new ContributionStore<PanelContribution>();
const statusBarStore = new ContributionStore<StatusBarContribution>();
const settingsStore = new ContributionStore<SettingsSectionContribution>();

let workbenchGeneration = 0;
const workbenchSubscribers = new Set<() => void>();

const notifyWorkbench = (): void => {
  workbenchGeneration += 1;
  for (const subscriber of workbenchSubscribers) {
    subscriber();
  }
};

const subscribeWorkbench = (subscriber: () => void): (() => void) => {
  workbenchSubscribers.add(subscriber);
  return () => workbenchSubscribers.delete(subscriber);
};

export const getWorkbenchGeneration = (): number => workbenchGeneration;

export const useWorkbenchGeneration = (): number =>
  useSyncExternalStore(subscribeWorkbench, getWorkbenchGeneration, getWorkbenchGeneration);

const contributionEnabled = (pluginId: string | undefined): boolean => {
  if (!pluginId) return true;
  return isPluginEnabled(pluginId);
};

const track = <T>(store: ContributionStore<T>, id: string, value: T): (() => void) => {
  const dispose = store.set(id, value);
  notifyWorkbench();
  return () => {
    dispose();
    notifyWorkbench();
  };
};

export const registerCommand = (spec: CommandContribution): (() => void) =>
  track(commandStore, spec.id, spec);

export const registerViewContainer = (spec: ViewContainerContribution): (() => void) =>
  track(viewContainerStore, spec.id, spec);

export const registerView = (spec: ViewContribution): (() => void) =>
  track(viewStore, spec.id, spec);

export const registerPanel = (spec: PanelContribution): (() => void) =>
  track(panelStore, spec.id, spec);

export const registerStatusBarItem = (spec: StatusBarContribution): (() => void) =>
  track(statusBarStore, spec.id, spec);

export const registerSettingsSection = (spec: SettingsSectionContribution): (() => void) =>
  track(settingsStore, spec.id, spec);

export const listCommands = (): CommandContribution[] =>
  commandStore
    .list()
    .filter((item) => contributionEnabled(item.pluginId))
    .filter((item) => (item.isVisible ? item.isVisible() : true));

export const getCommand = (id: string): CommandContribution | undefined => {
  const item = commandStore.get(id);
  if (!item || !contributionEnabled(item.pluginId)) return undefined;
  return item;
};

export const listViewContainers = (): ViewContainerContribution[] =>
  viewContainerStore
    .list()
    .filter((item) => contributionEnabled(item.pluginId))
    .slice()
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0));

export const listViews = (): ViewContribution[] =>
  viewStore
    .list()
    .filter((item) => contributionEnabled(item.pluginId))
    .slice()
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0));

/** Includes disabled plugins — used for path matching / stale URLs. */
export const listAllViewContainers = (): ViewContainerContribution[] => viewContainerStore.list();

export const listAllViews = (): ViewContribution[] => viewStore.list();

export const listBottomPanels = (): PanelContribution[] =>
  panelStore
    .list()
    .filter((item) => contributionEnabled(item.pluginId))
    .filter((item) => item.position === "bottom")
    .slice()
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0));

export const listStatusBarItems = (): StatusBarContribution[] =>
  statusBarStore
    .list()
    .filter((item) => contributionEnabled(item.pluginId))
    .slice()
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0));

export const listSettingsSections = (): SettingsSectionContribution[] =>
  settingsStore
    .list()
    .filter((item) => contributionEnabled(item.pluginId))
    .slice()
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0));

let bottomPanelRequest: { id: string; seq: number } | null = null;
let bottomPanelSeq = 0;
const bottomPanelListeners = new Set<() => void>();

export const openBottomPanel = (id: string): void => {
  bottomPanelRequest = { id, seq: ++bottomPanelSeq };
  for (const listener of bottomPanelListeners) listener();
};

export const getBottomPanelOpenRequest = (): { id: string; seq: number } | null =>
  bottomPanelRequest;

export const subscribeBottomPanelHost = (listener: () => void): (() => void) => {
  bottomPanelListeners.add(listener);
  return () => bottomPanelListeners.delete(listener);
};

export const resetWorkbenchContributionsForTests = (): void => {
  commandStore.clear();
  viewContainerStore.clear();
  viewStore.clear();
  panelStore.clear();
  statusBarStore.clear();
  settingsStore.clear();
  bottomPanelRequest = null;
  notifyWorkbench();
};
