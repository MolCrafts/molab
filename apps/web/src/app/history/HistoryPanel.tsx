/**
 * Workspace git history: the facts already recorded, plus sync and push.
 */

import { Input } from "@molcrafts/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type JSX, useState } from "react";
import { apiErrorMessage } from "@/api/errors";
import { historyApi } from "@/api/history";
import { SettingsRow } from "@/components/settings";
import { toast } from "@/components/ui/toast";
import {
  WorkbenchAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { formatDateTime } from "@/lib/datetime";

const historyKey = ["workspace-history"] as const;

export const HistoryPanel = (): JSX.Element => {
  const queryClient = useQueryClient();
  const history = useQuery({
    queryKey: historyKey,
    queryFn: () => historyApi.list(),
  });
  const [remote, setRemote] = useState("");
  const [busy, setBusy] = useState<"sync" | "push" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: historyKey });
  };

  const sync = async (): Promise<void> => {
    setBusy("sync");
    setError(null);
    try {
      const result = await historyApi.sync();
      toast.success(result.commit ? "History committed" : "Nothing to commit");
      await refresh();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not sync history."));
    } finally {
      setBusy(null);
    }
  };

  const push = async (): Promise<void> => {
    const target = remote.trim();
    if (!target) return;
    setBusy("push");
    setError(null);
    try {
      await historyApi.push(target);
      toast.success("History pushed");
    } catch (err) {
      setError(apiErrorMessage(err, "Could not push history."));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-3">
      <SettingsRow label="Record">
        <WorkbenchAction
          kind="secondary"
          size="compact"
          disabled={busy !== null}
          onClick={() => void sync()}
        >
          {busy === "sync" ? "Committing…" : "Commit pending changes"}
        </WorkbenchAction>
      </SettingsRow>
      <SettingsRow label="Backup">
        <div className="flex min-w-0 flex-1 gap-2">
          <Input
            value={remote}
            aria-label="Git remote"
            placeholder="git@host:lab.git"
            onChange={(event) => setRemote(event.target.value)}
          />
          <WorkbenchAction
            kind="secondary"
            size="compact"
            disabled={busy !== null || remote.trim() === ""}
            onClick={() => void push()}
          >
            {busy === "push" ? "Pushing…" : "Push"}
          </WorkbenchAction>
        </div>
      </SettingsRow>
      {error ? <p className="text-body text-destructive">{error}</p> : null}
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
      ) : history.data.length === 0 ? (
        <p className="text-label text-muted-foreground">No recorded facts.</p>
      ) : (
        <ul className="divide-y divide-border/60 border-y border-border/60">
          {history.data.map((fact) => (
            <li
              key={`${fact.commit}-${fact.subjectId}-${fact.event}`}
              className="grid gap-0.5 py-2"
            >
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-body text-foreground">{fact.summary || fact.event}</span>
                <time
                  dateTime={fact.occurredAt}
                  title={fact.occurredAt}
                  className="shrink-0 font-mono text-micro text-muted-foreground"
                >
                  {formatDateTime(fact.occurredAt)}
                </time>
              </div>
              <p className="font-mono text-micro text-muted-foreground">
                {fact.event} · {fact.subjectType} {fact.subjectId}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
