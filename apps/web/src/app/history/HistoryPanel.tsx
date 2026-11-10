/**
 * Settings › History (L11): three settings — Record (commit what changed),
 * Backup (push to a git remote), and Recorded facts (by day, newest first,
 * attempts named by their run title).
 */

import { Button, Input } from "@molcrafts/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type JSX, useMemo, useState } from "react";
import { apiErrorMessage } from "@/api/errors";
import { historyApi } from "@/api/history";
import { StatusIcon } from "@/app/components/entity";
import { useScopeRuns } from "@/app/dashboard/useScopeRuns";
import { withRunTitles } from "@/app/runs/runTitle";
import type { SettingEntry } from "@/app/settings/settingsModel";
import { SettingActions, SettingItem } from "@/components/settings";
import { toast } from "@/components/ui/toast";
import { WorkbenchOperationState, WorkbenchRetryAction } from "@/components/workbench";
import { formatDateTime } from "@/lib/datetime";
import { groupFactsByDay } from "./historyFacts";

const historyKey = ["workspace-history"] as const;
/** Facts shown before "Show N more". */
const FIRST_PAGE = 7;

const Record = ({ category }: { category?: string }): JSX.Element => {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const commit = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const result = await historyApi.sync();
      toast.success(result.commit ? "History committed" : "Nothing to commit");
      await queryClient.invalidateQueries({ queryKey: historyKey });
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not commit the history."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <SettingItem
      id="history-record"
      category={category}
      title="Record"
      description="Commit what changed since the last fact."
    >
      <SettingActions>
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => void commit()}>
          {busy ? "Committing…" : "Commit pending changes"}
        </Button>
      </SettingActions>
      {error ? (
        <p role="alert" className="text-label text-status-failed-foreground">
          {error}
        </p>
      ) : null}
    </SettingItem>
  );
};

const Backup = ({ category }: { category?: string }): JSX.Element => {
  const [remote, setRemote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const push = async (): Promise<void> => {
    const target = remote.trim();
    if (!target) return;
    setBusy(true);
    setError(null);
    try {
      await historyApi.push(target);
      toast.success("History pushed");
    } catch (cause) {
      setError(apiErrorMessage(cause, "Could not push the history."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <SettingItem
      id="history-backup"
      category={category}
      title="Backup"
      description="Push the history to a git remote."
    >
      <SettingActions>
        <Input
          value={remote}
          aria-label="Git remote"
          placeholder="git@host:lab.git"
          className="w-80 font-mono max-sm:w-full"
          onChange={(event) => setRemote(event.target.value)}
        />
        <Button
          size="sm"
          variant="secondary"
          disabled={busy || remote.trim() === ""}
          onClick={() => void push()}
        >
          {busy ? "Pushing…" : "Push"}
        </Button>
      </SettingActions>
      {error ? (
        <p role="alert" className="text-label text-status-failed-foreground">
          {error}
        </p>
      ) : null}
    </SettingItem>
  );
};

const RecordedFacts = ({ category }: { category?: string }): JSX.Element => {
  const history = useQuery({ queryKey: historyKey, queryFn: () => historyApi.list() });
  const inventory = useScopeRuns({}, true);
  const runs = useMemo(() => withRunTitles(inventory.rows), [inventory.rows]);
  const [showAll, setShowAll] = useState(false);
  const facts = history.data ?? [];
  const shown = showAll
    ? facts
    : [...facts].sort((a, b) => b.occurredAt.localeCompare(a.occurredAt)).slice(0, FIRST_PAGE);
  const days = useMemo(() => groupFactsByDay(shown, runs), [shown, runs]);
  const hidden = facts.length - shown.length;
  return (
    <SettingItem
      id="history-facts"
      category={category}
      title="Recorded facts"
      description={history.data ? `${facts.length} facts, newest first.` : undefined}
    >
      {history.isPending ? (
        <WorkbenchOperationState kind="loading" density="compact" title="Loading history…" />
      ) : history.isError ? (
        <WorkbenchOperationState
          kind="error"
          density="compact"
          title="Could not load history"
          detail={apiErrorMessage(history.error, "History is unavailable.")}
          action={<WorkbenchRetryAction onClick={() => void history.refetch()} />}
        />
      ) : facts.length === 0 ? (
        <p className="text-label text-muted-foreground">No recorded facts.</p>
      ) : (
        <div className="flex flex-col">
          {days.map((day) => (
            <div key={day.label} className="flex flex-col">
              <p className="pt-2 pb-1 text-label text-muted-foreground">{day.label}</p>
              <ul className="flex flex-col">
                {day.facts.map((item) => (
                  <li
                    key={item.key}
                    className="flex h-list-row min-w-0 items-center gap-2 text-body"
                  >
                    {item.status ? (
                      <StatusIcon status={item.status} />
                    ) : (
                      <span className="size-icon-sm flex-none" />
                    )}
                    <span className="min-w-0 flex-1 truncate" title={item.title}>
                      {item.title}
                    </span>
                    <span className="flex-none font-mono text-micro text-muted-foreground max-sm:hidden">
                      {item.event}
                    </span>
                    <time
                      dateTime={item.occurredAt}
                      title={formatDateTime(item.occurredAt)}
                      className="w-12 flex-none text-right text-label tabular-nums text-muted-foreground"
                    >
                      {new Date(item.occurredAt).toLocaleTimeString(undefined, {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </time>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {hidden > 0 ? (
            <SettingActions>
              <Button
                size="sm"
                variant="secondary"
                className="mt-2"
                onClick={() => setShowAll(true)}
              >
                Show {hidden} more
              </Button>
            </SettingActions>
          ) : null}
        </div>
      )}
    </SettingItem>
  );
};

export const HISTORY_ENTRIES: readonly SettingEntry[] = [
  {
    id: "history-record",
    title: "Record",
    description: "Commit what changed since the last fact.",
    keywords: ["commit", "git", "sync"],
    render: (category) => <Record key="record" category={category} />,
  },
  {
    id: "history-backup",
    title: "Backup",
    description: "Push the history to a git remote.",
    keywords: ["push", "git", "remote"],
    render: (category) => <Backup key="backup" category={category} />,
  },
  {
    id: "history-facts",
    title: "Recorded facts",
    description: "Every recorded fact, newest first.",
    keywords: ["log", "history", "provenance"],
    render: (category) => <RecordedFacts key="facts" category={category} />,
  },
];
