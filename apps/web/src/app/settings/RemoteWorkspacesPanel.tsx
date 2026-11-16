/**
 * Settings › Remote workspaces (L11): each workspace is a setting — its name
 * (Active when it is the one shown), "cluster · path · last test" as the
 * description, and Test connection / Make active or Refresh cache / Remove
 * under it; a test lists its checks right there. Adding is the last setting.
 */

import { Button } from "@molcrafts/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { type JSX, useState } from "react";
import type { WorkspaceTargetResponse } from "@/api/generated/models/WorkspaceTargetResponse";
import { WorkspaceService } from "@/api/generated/services/WorkspaceService";
import { usePermissions } from "@/app/auth";
import { SettingActions, SettingItem, SettingTag } from "@/components/settings";
import { emitWorkspaceSwitching } from "../state/workspaceSwitchEvents";
import { AddRemoteWorkspaceDialog } from "./AddRemoteWorkspaceDialog";
import { TestChecks, type TestOutcome, TestStatus } from "./ConnectionTest";
import { settingsKeys } from "./settingsKeys";
import type { SettingEntry } from "./settingsModel";

const message = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

/** The remote workspaces, for the side bar's count. */
export const useRemoteWorkspaces = () =>
  useQuery({
    queryKey: settingsKeys.remoteWorkspaces(),
    queryFn: async () => (await WorkspaceService.listWorkspaceTargets()).targets,
  });

export const useRemoteWorkspaceEntries = (): SettingEntry[] => {
  const { writeDeniedReason } = usePermissions();
  const queryClient = useQueryClient();
  const list = useRemoteWorkspaces();
  const [busy, setBusy] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<Record<string, TestOutcome>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [activeName, setActiveName] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [cacheNote, setCacheNote] = useState<string | null>(null);

  const invalidate = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: settingsKeys.remoteWorkspaces() });
  const remove = useMutation({
    mutationFn: (name: string) => WorkspaceService.deleteWorkspaceTarget(name),
    onSuccess: invalidate,
  });

  const run = async (
    name: string,
    action: () => Promise<void>,
    fallback: string,
  ): Promise<void> => {
    setBusy(name);
    setErrors(({ [name]: _cleared, ...rest }) => rest);
    try {
      await action();
    } catch (error) {
      setErrors((current) => ({ ...current, [name]: message(error, fallback) }));
    } finally {
      setBusy(null);
    }
  };

  const test = (name: string): Promise<void> =>
    run(
      name,
      async () => {
        const result = await WorkspaceService.testWorkspaceTarget(name);
        setOutcomes((current) => ({ ...current, [name]: { result, at: Date.now() } }));
      },
      "Could not test the connection",
    );
  const makeActive = (name: string): Promise<void> =>
    run(
      name,
      async () => {
        setWarnings([]);
        setCacheNote(null);
        const info = await WorkspaceService.openWorkspace({ kind: "remote", name });
        emitWorkspaceSwitching({ activeDescriptor: name });
        setActiveName(name);
        setWarnings(info.warnings ?? []);
      },
      "Could not switch the active workspace",
    );
  const refreshCache = (name: string): Promise<void> =>
    run(
      name,
      async () => {
        const result = await WorkspaceService.refreshWorkspaceCache({ scope: "indices" });
        setCacheNote(
          `Navigation cache refreshed — ${result.dropped} ${result.dropped === 1 ? "entry" : "entries"} dropped.`,
        );
        setWarnings(result.warnings ?? []);
      },
      "Could not refresh the navigation cache",
    );
  const removeOne = (name: string): Promise<void> =>
    run(
      name,
      async () => {
        await remove.mutateAsync(name);
        if (activeName === name) setActiveName(null);
      },
      "Could not remove the workspace",
    );

  const workspaceEntry = (target: WorkspaceTargetResponse): SettingEntry => {
    const active = target.name === activeName;
    const outcome = outcomes[target.name] ?? null;
    const disabled = busy === target.name || Boolean(writeDeniedReason);
    return {
      id: `remote:${target.name}`,
      title: target.name,
      description: `${target.clusterId} ${target.rootPath}`,
      keywords: ["remote workspace", target.registryId],
      render: (category) => (
        <SettingItem
          key={target.name}
          id={`remote-${target.name}`}
          category={category}
          title={target.name}
          tag={active ? <SettingTag>Active</SettingTag> : null}
          description={
            <span className="inline-flex flex-wrap items-center gap-1">
              {target.clusterId} · <span className="font-mono">{target.rootPath}</span> ·{" "}
              <TestStatus outcome={outcome} />
            </span>
          }
        >
          <SettingActions>
            <Button
              size="sm"
              variant="secondary"
              disabled={disabled}
              onClick={() => void test(target.name)}
            >
              Test connection
            </Button>
            {active ? (
              <Button
                size="sm"
                variant="secondary"
                disabled={disabled}
                onClick={() => void refreshCache(target.name)}
              >
                Refresh cache
              </Button>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                disabled={disabled}
                onClick={() => void makeActive(target.name)}
              >
                Make active
              </Button>
            )}
            <Button
              size="sm"
              variant="secondary"
              disabled={disabled || active}
              title={
                active ? "Make another workspace active first" : (writeDeniedReason ?? undefined)
              }
              onClick={() => void removeOne(target.name)}
            >
              Remove
            </Button>
          </SettingActions>
          <TestChecks outcome={outcome} />
          {errors[target.name] ? (
            <p role="alert" className="text-label text-status-failed-foreground">
              {errors[target.name]}
            </p>
          ) : null}
          {active && cacheNote ? (
            <p className="text-label text-muted-foreground">{cacheNote}</p>
          ) : null}
          {active && warnings.length ? <Warnings warnings={warnings} /> : null}
        </SettingItem>
      ),
    };
  };

  const statusEntry = (title: string, text: string, alert = false): SettingEntry => ({
    id: "remote:status",
    title,
    render: (category) => (
      <SettingItem key="status" category={category} title={title}>
        <p
          role={alert ? "alert" : undefined}
          className={
            alert ? "text-label text-status-failed-foreground" : "text-label text-muted-foreground"
          }
        >
          {text}
        </p>
      </SettingItem>
    ),
  });

  const add: SettingEntry = {
    id: "remote:add",
    title: "Add a remote workspace",
    description: "Serve a workspace that lives on another machine.",
    render: (category) => (
      <SettingItem
        key="add"
        id="remote-add"
        category={category}
        title="Add a remote workspace"
        description="Serve a workspace that lives on another machine."
      >
        <SettingActions>
          {writeDeniedReason ? (
            <Button size="sm" variant="secondary" disabled title={writeDeniedReason}>
              Add remote workspace
            </Button>
          ) : (
            <AddRemoteWorkspaceDialog
              trigger={
                <Button size="sm" variant="secondary">
                  Add remote workspace
                </Button>
              }
              onCreated={() => void invalidate()}
            />
          )}
        </SettingActions>
      </SettingItem>
    ),
  };

  if (list.isPending) return [statusEntry("Remote workspaces", "Loading…"), add];
  if (list.isError)
    return [
      statusEntry(
        "Remote workspaces",
        message(list.error, "Could not list remote workspaces"),
        true,
      ),
      add,
    ];
  if (list.data.length === 0)
    return [
      {
        id: "remote:none",
        title: "No remote workspaces",
        render: (category) => (
          <SettingItem
            key="none"
            category={category}
            title="No remote workspaces"
            description="The workbench shows the workspace this server was started in."
          />
        ),
      },
      add,
    ];
  return [...list.data.map(workspaceEntry), add];
};

const Warnings = ({ warnings }: { warnings: string[] }): JSX.Element => (
  <div className="flex flex-col gap-1 rounded-md bg-status-warning-soft px-3 py-2 text-label">
    <span className="flex items-center gap-2 font-medium text-status-warning-foreground">
      <AlertTriangle aria-hidden className="size-icon-sm" />
      {warnings.length} {warnings.length === 1 ? "warning" : "warnings"} while fetching the
      navigation tree
    </span>
    <ul className="flex flex-col gap-1 text-muted-foreground">
      {warnings.map((warning) => (
        <li key={warning} className="break-all">
          {warning}
        </li>
      ))}
    </ul>
  </div>
);
