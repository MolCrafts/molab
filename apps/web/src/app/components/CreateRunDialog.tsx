import {
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@molcrafts/ui";
import { Plus } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";
import { runsApi } from "@/api";
import type { TargetResponse } from "@/api/generated/models/TargetResponse";
import { ExperimentsService } from "@/api/generated/services/ExperimentsService";
import { TargetsService } from "@/api/generated/services/TargetsService";
import { ParametersForm } from "@/app/runs/ParametersForm";
import {
  type InputField,
  parseInputSchema,
  SchemaForm,
  schemaDefaults,
} from "@/app/runs/SchemaForm";
import { AddTargetDialog } from "@/app/settings/AddTargetDialog";
import { AppDialog } from "@/components/dialog/AppDialog";
import { WorkbenchIconAction } from "@/components/workbench";

const NO_TARGET_VALUE = "__none__";

interface CreateRunDialogProps {
  projectId: string;
  experimentId: string;
  workflowFile: string;
  /** Called with the new run id so the parent can navigate into it. */
  onRunCreated: (runId: string) => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  trigger?: ReactNode;
}

export function CreateRunDialog({
  projectId,
  experimentId,
  workflowFile,
  onRunCreated,
  open: controlledOpen,
  onOpenChange,
  trigger,
}: CreateRunDialogProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const [parameters, setParameters] = useState<Record<string, unknown>>({});
  const [assetInputs, setAssetInputs] = useState("");
  const [inputSchema, setInputSchema] = useState<InputField[] | null>(null);
  const [target, setTarget] = useState<string>(NO_TARGET_VALUE);
  const [targets, setTargets] = useState<TargetResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = controlledOpen ?? uncontrolledOpen;
  const setOpen = onOpenChange ?? setUncontrolledOpen;

  const refreshTargets = useCallback(async () => {
    try {
      const res = await TargetsService.listTargetsEndpoint();
      setTargets(res.targets);
    } catch {
      setTargets([]);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void refreshTargets();
    void ExperimentsService.getExperiment(projectId, experimentId)
      .then((exp) => {
        if (exp.defaultTarget) setTarget(exp.defaultTarget);
        const schema = parseInputSchema(exp.workflow);
        setInputSchema(schema);
        if (schema) setParameters(schemaDefaults(schema));
      })
      .catch(() => {
        // experiment may not yet be readable; ignore
      });
  }, [open, projectId, experimentId, refreshTargets]);

  const handleSubmit = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const created = await runsApi.createScopedRun(projectId, experimentId, {
        params: parameters,
        inputs: assetInputs.split(/[\s,]+/).filter(Boolean),
        target: target === NO_TARGET_VALUE ? null : target,
      });

      setOpen(false);
      setParameters({});
      setAssetInputs("");
      setTarget(NO_TARGET_VALUE);
      onRunCreated(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AppDialog
      open={open}
      onOpenChange={setOpen}
      title="New run"
      size="wide"
      primaryLabel="Create run"
      busyLabel="Creating…"
      busy={isLoading}
      onPrimary={handleSubmit}
      error={error}
      trigger={
        trigger === undefined ? (
          <WorkbenchIconAction label="New run">
            <Plus className="size-3.5" />
          </WorkbenchIconAction>
        ) : (
          trigger
        )
      }
    >
      <div className="grid gap-2">
        <Label htmlFor="run-workflow">Workflow</Label>
        <Input id="run-workflow" value={workflowFile} disabled className="bg-muted" />
      </div>
      <div className="grid gap-2">
        <p className="text-label font-medium">{inputSchema ? "Inputs" : "Parameters"}</p>
        {inputSchema ? (
          <SchemaForm schema={inputSchema} value={parameters} onChange={setParameters} />
        ) : (
          <ParametersForm value={parameters} onChange={setParameters} />
        )}
      </div>
      <div className="grid gap-2">
        <Label htmlFor="run-assets">Assets</Label>
        <div className="grid gap-1">
          <Input
            id="run-assets"
            value={assetInputs}
            onChange={(event) => setAssetInputs(event.target.value)}
            placeholder="Asset ids, separated by space"
          />
          <p className="text-micro text-muted-foreground">
            Files this run opens. Each id is bound into the root task as a path.
          </p>
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="run-target">Target</Label>
        <div className="flex items-center gap-2">
          <Select value={target} onValueChange={setTarget}>
            <SelectTrigger id="run-target" className="min-w-0 flex-1">
              <SelectValue placeholder="No target — local in-process" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_TARGET_VALUE}>No target (local)</SelectItem>
              {targets.map((t) => (
                <SelectItem key={t.name} value={t.name}>
                  <span className="flex items-center gap-2">
                    <span className="font-medium">{t.name}</span>
                    <span className="text-micro uppercase tracking-wide text-muted-foreground">
                      {t.isRemote ? "remote" : "local"}
                    </span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <AddTargetDialog
            trigger={
              <WorkbenchIconAction label="Add new target">
                <Plus className="size-3.5" />
              </WorkbenchIconAction>
            }
            onCreated={(t) => {
              void refreshTargets();
              setTarget(t.name);
            }}
          />
        </div>
      </div>
    </AppDialog>
  );
}
