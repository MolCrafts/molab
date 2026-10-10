import { useSyncExternalStore } from "react";
import type { RendererKey } from "@/app/types";
import { ContributionRegistry } from "@/lib/contribution-registry";
import type {
  EntityTabContribution,
  ExecutionColumnContribution,
  ExecutionDetailContribution,
  FilePreviewPlugin,
  FileTypeContribution,
  MetricReaderContribution,
  RendererContribution,
  RendererResolutionContext,
} from "@/lib/contribution-types";
import { buildRendererRegistryKey } from "@/lib/contribution-types";
import { isPluginEnabled } from "@/lib/plugin-preferences";

const rendererRegistry = new ContributionRegistry<RendererContribution>("Renderer contribution");
const filePreviewRegistry = new ContributionRegistry<FilePreviewPlugin>("File preview plugin");
const entityTabRegistry = new ContributionRegistry<EntityTabContribution>(
  "Entity tab contribution",
);
const fileTypeRegistry = new ContributionRegistry<FileTypeContribution>("File type contribution");
const executionColumnRegistry = new ContributionRegistry<ExecutionColumnContribution>(
  "Execution column contribution",
);
const executionDetailRegistry = new ContributionRegistry<ExecutionDetailContribution>(
  "Execution detail contribution",
);

let contributionGeneration = 0;
const contributionSubscribers = new Set<() => void>();

const notifyContributionChange = (): void => {
  contributionGeneration += 1;
  for (const subscriber of contributionSubscribers) {
    subscriber();
  }
};

const subscribeToContributions = (subscriber: () => void): (() => void) => {
  contributionSubscribers.add(subscriber);
  return () => contributionSubscribers.delete(subscriber);
};

export const getContributionGeneration = (): number => contributionGeneration;

/** Re-render hosts when a lazily loaded plugin adds a contribution. */
export const useContributionGeneration = (): number =>
  useSyncExternalStore(
    subscribeToContributions,
    getContributionGeneration,
    getContributionGeneration,
  );

/**
 * Active plugin id while a plugin's `register()` runs. Contributions
 * registered inside that window inherit `pluginId` so the user can later
 * disable the whole plugin's panel surface.
 */
let activePluginId: string | null = null;

export const runWithPluginContext = <T>(pluginId: string, fn: () => T): T => {
  const previous = activePluginId;
  activePluginId = pluginId;
  try {
    return fn();
  } finally {
    activePluginId = previous;
  }
};

export const getActivePluginId = (): string | null => activePluginId;

const stampPluginId = <T extends { pluginId?: string }>(item: T): T => {
  if (item.pluginId) {
    return item;
  }
  if (!activePluginId) {
    return item;
  }
  return { ...item, pluginId: activePluginId };
};

/** Contributions without a pluginId are always enabled (legacy / host). */
const contributionEnabled = (pluginId: string | undefined): boolean => {
  if (!pluginId) {
    return true;
  }
  return isPluginEnabled(pluginId);
};

export const registerRendererContribution = (contribution: RendererContribution): void => {
  rendererRegistry.register(stampPluginId(contribution));
  notifyContributionChange();
};

export const unregisterRendererContribution = (id: string): boolean => {
  const removed = rendererRegistry.unregister(id);
  if (removed) notifyContributionChange();
  return removed;
};

export const resolveRendererContribution = (
  key: RendererKey,
  context?: Omit<RendererResolutionContext, "key">,
): RendererContribution | null => {
  const registryKey = buildRendererRegistryKey(key);

  const matches = rendererRegistry
    .getAll()
    .filter((contribution) => contributionEnabled(contribution.pluginId))
    .filter((contribution) => buildRendererRegistryKey(contribution.key) === registryKey)
    .filter((contribution) => {
      if (!contribution.matches) {
        return true;
      }
      if (!context) {
        return false;
      }
      return contribution.matches({ key, ...context });
    })
    .sort((left, right) => (right.priority ?? 0) - (left.priority ?? 0));

  return matches[0] ?? null;
};

export const registerFilePreviewContribution = (plugin: FilePreviewPlugin): void => {
  filePreviewRegistry.register(stampPluginId(plugin), { onDuplicate: "skip" });
  notifyContributionChange();
};

export const unregisterFilePreviewContribution = (pluginId: string): boolean => {
  const removed = filePreviewRegistry.unregister(pluginId);
  if (removed) notifyContributionChange();
  return removed;
};

export const listFilePreviewContributions = (): FilePreviewPlugin[] => {
  return filePreviewRegistry
    .getAll()
    .filter((plugin) => contributionEnabled(plugin.pluginId))
    .sort((left, right) => (right.priority ?? 0) - (left.priority ?? 0));
};

export const registerEntityTabContribution = (contribution: EntityTabContribution): void => {
  entityTabRegistry.register(stampPluginId(contribution), { onDuplicate: "skip" });
  notifyContributionChange();
};

export const unregisterEntityTabContribution = (contributionId: string): boolean => {
  const removed = entityTabRegistry.unregister(contributionId);
  if (removed) notifyContributionChange();
  return removed;
};

export const listEntityTabContributions = (
  objectType: EntityTabContribution["objectType"],
): EntityTabContribution[] => {
  return entityTabRegistry
    .getAll()
    .filter((contribution) => contributionEnabled(contribution.pluginId))
    .filter((contribution) => contribution.objectType === objectType)
    .sort((left, right) => (right.priority ?? 0) - (left.priority ?? 0));
};

export const registerFileTypeContribution = (contribution: FileTypeContribution): void => {
  fileTypeRegistry.register(stampPluginId(contribution), { onDuplicate: "skip" });
  notifyContributionChange();
};

export const unregisterFileTypeContribution = (contributionId: string): boolean => {
  const removed = fileTypeRegistry.unregister(contributionId);
  if (removed) notifyContributionChange();
  return removed;
};

export const listFileTypeContributions = (
  objectType: FileTypeContribution["objectType"],
): FileTypeContribution[] => {
  return fileTypeRegistry
    .getAll()
    .filter((contribution) => contributionEnabled(contribution.pluginId))
    .filter((contribution) => contribution.objectType === objectType)
    .sort((left, right) => (right.priority ?? 0) - (left.priority ?? 0));
};

export const registerExecutionColumnContribution = (
  contribution: ExecutionColumnContribution,
): void => {
  executionColumnRegistry.register(stampPluginId(contribution), { onDuplicate: "skip" });
  notifyContributionChange();
};

export const unregisterExecutionColumnContribution = (contributionId: string): boolean => {
  const removed = executionColumnRegistry.unregister(contributionId);
  if (removed) notifyContributionChange();
  return removed;
};

export const listExecutionColumnContributions = (
  backend?: string | null,
): ExecutionColumnContribution[] => {
  return executionColumnRegistry
    .getAll()
    .filter((c) => contributionEnabled(c.pluginId))
    .filter((c) => !c.backend || (backend && c.backend.toLowerCase() === backend.toLowerCase()))
    .sort((left, right) => (right.priority ?? 0) - (left.priority ?? 0));
};

export const registerExecutionDetailContribution = (
  contribution: ExecutionDetailContribution,
): void => {
  executionDetailRegistry.register(stampPluginId(contribution), { onDuplicate: "skip" });
  notifyContributionChange();
};

export const unregisterExecutionDetailContribution = (contributionId: string): boolean => {
  const removed = executionDetailRegistry.unregister(contributionId);
  if (removed) notifyContributionChange();
  return removed;
};

export const listExecutionDetailContributions = (
  backend?: string | null,
): ExecutionDetailContribution[] => {
  return executionDetailRegistry
    .getAll()
    .filter((c) => contributionEnabled(c.pluginId))
    .filter((c) => !c.backend || (backend && c.backend.toLowerCase() === backend.toLowerCase()))
    .sort((left, right) => (right.priority ?? 0) - (left.priority ?? 0));
};

export const resetContributionRuntimeForTests = (): void => {
  rendererRegistry.clear();
  filePreviewRegistry.clear();
  entityTabRegistry.clear();
  fileTypeRegistry.clear();
  executionColumnRegistry.clear();
  executionDetailRegistry.clear();
  activePluginId = null;
  notifyContributionChange();
};

const metricReaderRegistry = new ContributionRegistry<MetricReaderContribution>(
  "Metric reader contribution",
);

/** Register a format a viewer can plot. Contributed by whoever owns it. */
export const registerMetricReaderContribution = (contribution: MetricReaderContribution): void => {
  metricReaderRegistry.register(stampPluginId(contribution), { onDuplicate: "replace" });
  notifyContributionChange();
};

export const unregisterMetricReaderContribution = (contributionId: string): boolean => {
  const removed = metricReaderRegistry.unregister(contributionId);
  if (removed) notifyContributionChange();
  return removed;
};

/** Every enabled reader, most specific first. */
export const listMetricReaderContributions = (): MetricReaderContribution[] =>
  metricReaderRegistry
    .getAll()
    .filter((contribution) => contributionEnabled(contribution.pluginId))
    .sort((left, right) => (right.priority ?? 0) - (left.priority ?? 0));

/**
 * The reader whose patterns claim *path*, or `undefined`.
 *
 * Name-only: this is what decides whether to offer a chart before fetching
 * anything. Once the bytes are in hand, {@link resolveMetricReaderForText}
 * has the final say.
 */
export const resolveMetricReaderForPath = (path: string): MetricReaderContribution | undefined => {
  const normalized = path.toLowerCase().replace(/\\/g, "/");
  const name = normalized.split("/").pop() ?? normalized;
  return listMetricReaderContributions().find((contribution) =>
    contribution.patterns.some((pattern) => {
      const regex = globToRegExp(pattern.toLowerCase());
      return regex.test(normalized) || regex.test(name);
    }),
  );
};

/** The reader that both claims *path* by name and confirms *text* by content. */
export const resolveMetricReaderForText = (
  path: string,
  text: string,
): MetricReaderContribution | undefined => {
  const byName = resolveMetricReaderForPath(path);
  if (byName && (byName.claims?.(text) ?? true)) {
    return byName;
  }
  return listMetricReaderContributions().find((contribution) => contribution.claims?.(text));
};

/**
 * Compile one glob to a regex.
 *
 * Only the constructs a reader actually declares are supported — `**` spans
 * any number of leading segments, `*` stays inside one, `?` is one character
 * — because these describe file-name shapes, not arbitrary path expressions.
 */
const globToRegExp = (pattern: string): RegExp => {
  let source = "";
  for (let index = 0; index < pattern.length; index += 1) {
    const char = pattern[index];
    if (char === "*") {
      if (pattern[index + 1] === "*") {
        index += pattern[index + 2] === "/" ? 2 : 1;
        source += "(?:.*/)?";
        continue;
      }
      source += "[^/]*";
      continue;
    }
    if (char === "?") {
      source += "[^/]";
      continue;
    }
    source += char.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${source}$`);
};
