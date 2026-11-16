/**
 * Settings › Compute targets (L11): each target is a setting — its name,
 * "Local / cluster · scratch path · last test" as the description, and Test
 * connection / Remove under it; a test lists its checks right there. Adding
 * is the last setting.
 */

import { Button } from "@molcrafts/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { TargetResponse } from "@/api/generated/models/TargetResponse";
import { TargetsService } from "@/api/generated/services/TargetsService";
import { usePermissions } from "@/app/auth";
import { SettingActions, SettingItem } from "@/components/settings";
import { AddTargetDialog } from "./AddTargetDialog";
import { TestChecks, type TestOutcome, TestStatus } from "./ConnectionTest";
import { settingsKeys } from "./settingsKeys";
import type { SettingEntry } from "./settingsModel";

const message = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

export const useComputeTargets = () =>
  useQuery({
    queryKey: settingsKeys.computeTargets(),
    queryFn: async () => (await TargetsService.listTargetsEndpoint()).targets,
  });

export const useComputeTargetEntries = (): SettingEntry[] => {
  const { writeDeniedReason } = usePermissions();
  const queryClient = useQueryClient();
  const list = useComputeTargets();
  const [busy, setBusy] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<Record<string, TestOutcome>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const invalidate = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: settingsKeys.computeTargets() });
  const remove = useMutation({
    mutationFn: (name: string) => TargetsService.deleteTargetEndpoint(name),
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

  const targetEntry = (target: TargetResponse): SettingEntry => {
    const outcome = outcomes[target.name] ?? null;
    const disabled = busy === target.name || Boolean(writeDeniedReason);
    const where = target.isRemote ? (target.clusterId ?? "Remote") : "Local";
    return {
      id: `target:${target.name}`,
      title: target.name,
      description: `${where} ${target.scratchRoot}`,
      keywords: ["compute target"],
      render: (category) => (
        <SettingItem
          key={target.name}
          id={`target-${target.name}`}
          category={category}
          title={target.name}
          description={
            <span className="inline-flex flex-wrap items-center gap-1">
              {where} · <span className="font-mono">{target.scratchRoot}</span> ·{" "}
              <TestStatus outcome={outcome} />
            </span>
          }
        >
          <SettingActions>
            <Button
              size="sm"
              variant="secondary"
              disabled={disabled}
              onClick={() =>
                void run(
                  target.name,
                  async () => {
                    const result = await TargetsService.testTargetEndpoint(target.name);
                    setOutcomes((current) => ({
                      ...current,
                      [target.name]: { result, at: Date.now() },
                    }));
                  },
                  "Could not test the target",
                )
              }
            >
              Test connection
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={disabled}
              title={writeDeniedReason ?? undefined}
              onClick={() =>
                void run(
                  target.name,
                  () => remove.mutateAsync(target.name).then(() => undefined),
                  "Could not remove the target",
                )
              }
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
        </SettingItem>
      ),
    };
  };

  const add: SettingEntry = {
    id: "target:add",
    title: "Add a compute target",
    description: "A local directory, or a cluster reached over SSH.",
    render: (category) => (
      <SettingItem
        key="add"
        id="target-add"
        category={category}
        title="Add a compute target"
        description="A local directory, or a cluster reached over SSH."
      >
        <SettingActions>
          {writeDeniedReason ? (
            <Button size="sm" variant="secondary" disabled title={writeDeniedReason}>
              Add compute target
            </Button>
          ) : (
            <AddTargetDialog
              trigger={
                <Button size="sm" variant="secondary">
                  Add compute target
                </Button>
              }
              onCreated={() => void invalidate()}
            />
          )}
        </SettingActions>
      </SettingItem>
    ),
  };

  if (list.isPending || list.isError) {
    const text = list.isPending
      ? "Loading…"
      : message(list.error, "Could not list compute targets");
    return [
      {
        id: "target:status",
        title: "Compute targets",
        render: (category) => (
          <SettingItem key="status" category={category} title="Compute targets">
            <p
              role={list.isError ? "alert" : undefined}
              className={
                list.isError
                  ? "text-label text-status-failed-foreground"
                  : "text-label text-muted-foreground"
              }
            >
              {text}
            </p>
          </SettingItem>
        ),
      },
      add,
    ];
  }
  if (list.data.length === 0)
    return [
      {
        id: "target:none",
        title: "No compute targets",
        render: (category) => (
          <SettingItem
            key="none"
            category={category}
            title="No compute targets"
            description="Runs execute locally until a target is added."
          />
        ),
      },
      add,
    ];
  return [...list.data.map(targetEntry), add];
};
