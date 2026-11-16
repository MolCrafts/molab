import {
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@molcrafts/ui";
import { Plus } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";
import { experimentsApi } from "@/api";
import type { TargetResponse } from "@/api/generated/models/TargetResponse";
import { TargetsService } from "@/api/generated/services/TargetsService";
import { parseWorkflowDocumentInput } from "@/app/components/workflowDocumentInput";
import { AddTargetDialog } from "@/app/settings/AddTargetDialog";
import { AppDialog } from "@/components/dialog/AppDialog";
import { WorkbenchIconAction } from "@/components/workbench";

const NO_TARGET_VALUE = "__none__";

interface CreateExperimentDialogProps {
  projectId: string;
  onExperimentCreated: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  trigger?: ReactNode;
}

export function CreateExperimentDialog({
  projectId,
  onExperimentCreated,
  open: controlledOpen,
  onOpenChange,
  trigger,
}: CreateExperimentDialogProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const [name, setName] = useState("");
  const [workflow, setWorkflow] = useState("");
  const [description, setDescription] = useState("");
  const [parameterSpace, setParameterSpace] = useState("{}");
  const [defaultTarget, setDefaultTarget] = useState<string>(NO_TARGET_VALUE);
  const [targets, setTargets] = useState<TargetResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
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
  }, [open, refreshTargets]);

  const handleSubmit = async () => {
    const parsed = parseWorkflowDocumentInput(workflow);
    if (!parsed.ok) {
      setWorkflowError(parsed.error);
      return;
    }
    setWorkflowError(null);
    setIsLoading(true);
    setError(null);

    try {
      await experimentsApi.createExperiment(projectId, {
        name,
        workflowSource: parsed.document,
        description,
        parameterSpace: JSON.parse(parameterSpace),
        defaultTarget: defaultTarget === NO_TARGET_VALUE ? null : defaultTarget,
      });

      setOpen(false);
      setName("");
      setWorkflow("");
      setDescription("");
      setParameterSpace("{}");
      setDefaultTarget(NO_TARGET_VALUE);
      onExperimentCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create experiment");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AppDialog
      open={open}
      onOpenChange={setOpen}
      title="New experiment"
      size="wide"
      primaryLabel="Create experiment"
      busyLabel="Creating…"
      busy={isLoading}
      primaryDisabled={!name}
      onPrimary={handleSubmit}
      error={error}
      trigger={
        trigger === undefined ? (
          <WorkbenchIconAction label="New experiment">
            <Plus className="size-3.5" />
          </WorkbenchIconAction>
        ) : (
          trigger
        )
      }
    >
      <div className="grid gap-2">
        <Label htmlFor="exp-name">Name</Label>
        <Input id="exp-name" value={name} onChange={(e) => setName(e.target.value)} required />
      </div>
      <div className="grid gap-2">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Label htmlFor="exp-workflow" className="w-fit">
                Workflow IR (JSON)
              </Label>
            </TooltipTrigger>
            <TooltipContent side="left">
              Optional. Leave blank to start with an empty canvas.
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <Textarea
          id="exp-workflow"
          value={workflow}
          onChange={(e) => setWorkflow(e.target.value)}
          className="font-mono text-label"
          rows={4}
          aria-invalid={workflowError ? true : undefined}
        />
        {workflowError ? (
          <p
            className="flex items-center gap-1 text-label text-status-failed-foreground"
            role="alert"
          >
            {workflowError}
          </p>
        ) : null}
      </div>
      <div className="grid gap-2">
        <Label htmlFor="exp-params">Parameters (JSON)</Label>
        <Textarea
          id="exp-params"
          value={parameterSpace}
          onChange={(e) => setParameterSpace(e.target.value)}
          className="font-mono text-label"
          rows={4}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="exp-target">Default target</Label>
        <div className="flex items-center gap-2">
          <Select value={defaultTarget} onValueChange={setDefaultTarget}>
            <SelectTrigger id="exp-target" className="min-w-0 flex-1">
              <SelectValue placeholder="No default — pick at run time" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_TARGET_VALUE}>No default</SelectItem>
              {targets.map((t) => (
                <SelectItem key={t.name} value={t.name}>
                  <span className="flex items-center gap-2">
                    <span className="font-medium">{t.name}</span>
                    <span className="text-label font-medium text-muted-foreground">
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
              setDefaultTarget(t.name);
            }}
          />
        </div>
      </div>
    </AppDialog>
  );
}
