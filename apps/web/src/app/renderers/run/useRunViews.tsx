/**
 * The run page's plugin views (L14): every registered run view whose `files`
 * the page's attempt has (or that has no `files`), in tab order, with its
 * count badge; and the host services each view reaches through the
 * `@molcrafts/molab-plugin/ui` hooks.
 */

import type {
  AttemptFile,
  AttemptRead,
  RunAttempt,
  RunViewContribution,
  RunViewHost,
} from "@molcrafts/molab-plugin";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import {
  runFileBlobQueryOptions,
  runFilesQueryOptions,
  runFileTextQueryOptions,
} from "@/app/state/entityQueries";
import { listRunViewContributions, useContributionGeneration } from "@/lib/contribution-runtime";
import { flattenFileNodes, matchesMatcher } from "@/lib/file-type-discovery";
import { usePluginPreferencesGeneration } from "@/lib/plugin-preferences";

export interface RunViewTab {
  contribution: RunViewContribution;
  files: readonly AttemptFile[];
  count: number | null;
}

/** Views that apply to *files*: no matcher, or at least one matching file. */
export const applicableRunViews = (
  contributions: readonly RunViewContribution[],
  files: readonly AttemptFile[],
): { contribution: RunViewContribution; files: AttemptFile[] }[] =>
  contributions.flatMap((contribution) => {
    if (!contribution.files) return [{ contribution, files: [] }];
    const matcher = contribution.files;
    const matched = files.filter((file) => matchesMatcher(matcher, file));
    return matched.length > 0 ? [{ contribution, files: matched }] : [];
  });

export const useRunViews = (
  attempt: RunAttempt | null,
): { tabs: RunViewTab[]; dir: string | null; loading: boolean } => {
  const prefs = usePluginPreferencesGeneration();
  const generation = useContributionGeneration();
  const listing = useQuery({
    ...runFilesQueryOptions(
      attempt?.projectId ?? "",
      attempt?.experimentId ?? "",
      attempt?.runId ?? "",
      attempt?.executionId ?? "",
    ),
    enabled: Boolean(attempt),
  });
  const applicable = useMemo(() => {
    void prefs;
    void generation;
    const files = listing.data ? flattenFileNodes(listing.data.nodes) : [];
    return applicableRunViews(listRunViewContributions(), files);
  }, [listing.data, prefs, generation]);
  const counts = useQueries({
    queries: applicable.map(({ contribution, files }) => ({
      queryKey: [
        "run-view-count",
        contribution.id,
        attempt?.runId,
        attempt?.executionId,
        files.length,
      ],
      queryFn: async () =>
        attempt && contribution.count ? ((await contribution.count(attempt, files)) ?? null) : null,
      enabled: Boolean(attempt && contribution.count),
      staleTime: 30_000,
    })),
  });
  const tabs = applicable.map((view, index) => ({
    ...view,
    count: (counts[index]?.data as number | null | undefined) ?? null,
  }));
  return { tabs, dir: listing.data?.runDir ?? null, loading: listing.isPending };
};

const read = <T,>(query: {
  data: T | undefined;
  isPending: boolean;
  isFetching: boolean;
  error: unknown;
  refetch: () => unknown;
}): AttemptRead<T> => ({
  data: query.data,
  loading: query.isPending && query.isFetching,
  error: query.error
    ? query.error instanceof Error
      ? query.error.message
      : String(query.error)
    : null,
  refetch: () => void query.refetch(),
});

/** The services a run view reaches; hooks inside are stable functions. */
export const useRunViewHost = (
  attempt: RunAttempt | null,
  links: { openFile: (path: string) => void; openLogs: (line?: number) => void },
): RunViewHost | null =>
  useMemo(() => {
    if (!attempt) return null;
    const { projectId, experimentId, runId, executionId } = attempt;
    const useAttemptText = (path: string | null): AttemptRead<string> =>
      read(
        useQuery({
          ...runFileTextQueryOptions(projectId, experimentId, runId, executionId, path ?? ""),
          enabled: Boolean(path),
        }),
      );
    const useAttemptBlob = (path: string | null): AttemptRead<string> => {
      const query = useQuery({
        ...runFileBlobQueryOptions(projectId, experimentId, runId, executionId, path ?? ""),
        enabled: Boolean(path),
      });
      const url = useMemo(
        () => (query.data ? URL.createObjectURL(query.data) : undefined),
        [query.data],
      );
      useEffect(
        () => () => {
          if (url) URL.revokeObjectURL(url);
        },
        [url],
      );
      return { ...read(query), data: url };
    };
    return {
      attempt,
      useAttemptText,
      useAttemptBlob,
      openFile: links.openFile,
      openLogs: links.openLogs,
    };
  }, [attempt, links.openFile, links.openLogs]);
