import { Input, Label } from "@molcrafts/ui";
import { Plus } from "lucide-react";
import { useState } from "react";
import { projectsApi } from "@/api";
import { AppDialog } from "@/components/dialog/AppDialog";
import { WorkbenchIconAction } from "@/components/workbench";

interface CreateProjectDialogProps {
  onProjectCreated: () => void;
  /** When set, the trigger is disabled and hover explains why. */
  writeDeniedReason?: string | null;
  /** Controlled open (e.g. from tree context menu). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Show the header + button. Default true. */
  showTrigger?: boolean;
}

export function CreateProjectDialog({
  onProjectCreated,
  writeDeniedReason,
  open: controlledOpen,
  onOpenChange: controlledOnOpenChange,
  showTrigger = true,
}: CreateProjectDialogProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const open = controlledOpen ?? uncontrolledOpen;
  const setOpen = controlledOnOpenChange ?? setUncontrolledOpen;
  const [name, setName] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (writeDeniedReason) return;
    setIsLoading(true);
    setError(null);

    try {
      await projectsApi.createProject({
        name,
        description: "",
      });

      setOpen(false);
      setName("");
      onProjectCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      {showTrigger && writeDeniedReason ? (
        <WorkbenchIconAction
          label="New project"
          kind="ghost"
          className="h-control-compact w-control-compact"
          aria-label="New project"
          deniedReason={writeDeniedReason}
        >
          <Plus className="size-icon" />
        </WorkbenchIconAction>
      ) : null}
      <AppDialog
        open={open}
        onOpenChange={setOpen}
        title="New project"
        size="form"
        primaryLabel="Create project"
        busyLabel="Creating…"
        busy={isLoading}
        primaryDisabled={!name}
        onPrimary={handleSubmit}
        error={error}
        trigger={
          showTrigger && !writeDeniedReason ? (
            <WorkbenchIconAction
              label="New project"
              kind="ghost"
              className="h-control-compact w-control-compact"
              aria-label="New project"
            >
              <Plus className="size-icon" />
            </WorkbenchIconAction>
          ) : undefined
        }
      >
        <div className="grid gap-2">
          <Label htmlFor="name">Name</Label>
          <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
      </AppDialog>
    </>
  );
}
