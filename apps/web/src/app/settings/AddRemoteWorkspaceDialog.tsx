/**
 * Modal dialog that registers a remote workspace. Mirrors AddTargetDialog
 * for consistency with the Compute targets flow.
 */

import {
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@molcrafts/ui";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useState } from "react";
import { WorkspaceTargetCreateRequest } from "@/api/generated/models/WorkspaceTargetCreateRequest";
import type { WorkspaceTargetResponse } from "@/api/generated/models/WorkspaceTargetResponse";
import { MolqService } from "@/api/generated/services/MolqService";
import { WorkspaceService } from "@/api/generated/services/WorkspaceService";
import { AppDialog } from "@/components/dialog/AppDialog";

interface AddRemoteWorkspaceDialogProps {
  trigger: ReactNode;
  onCreated?: (target: WorkspaceTargetResponse) => void;
}

export function AddRemoteWorkspaceDialog({
  trigger,
  onCreated,
}: AddRemoteWorkspaceDialogProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [clusterId, setClusterId] = useState("");
  const [root, setRoot] = useState("");
  const [cacheMode, setCacheMode] = useState(WorkspaceTargetCreateRequest.cacheMode.PINNED);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const destinations = useQuery({
    queryKey: ["molq", "destinations"],
    queryFn: () => MolqService.listDestinations(),
    enabled: open,
  });

  // The fields start empty each time, as they did when the form unmounted on close.
  const changeOpen = (next: boolean): void => {
    setOpen(next);
    if (next) return;
    setName("");
    setClusterId("");
    setRoot("");
    setCacheMode(WorkspaceTargetCreateRequest.cacheMode.PINNED);
    setError(null);
  };

  const handleSubmit = async (): Promise<void> => {
    if (!destinations.data || !clusterId) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload: WorkspaceTargetCreateRequest = {
        name: name.trim(),
        rootPath: root.trim(),
        registryId: destinations.data.registryId,
        clusterId,
        cacheMode,
      };
      const created = await WorkspaceService.createWorkspaceTarget(payload);
      changeOpen(false);
      onCreated?.(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add remote workspace");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppDialog
      open={open}
      onOpenChange={changeOpen}
      title="Add remote workspace"
      message="Register a remote workspace root reachable over SSH. The remote directory must already exist — this descriptor only tells molab how to reach it."
      size="form"
      primaryLabel="Add workspace"
      busyLabel="Adding…"
      busy={submitting}
      primaryDisabled={!clusterId || !destinations.data || !name || !root}
      onPrimary={handleSubmit}
      error={error}
      trigger={trigger}
    >
      <div className="grid gap-2">
        <Label htmlFor="AddRemoteWorkspaceForm-name">Name</Label>
        <Input
          id="AddRemoteWorkspaceForm-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="AddRemoteWorkspaceForm-destination">Destination</Label>
        <Select value={clusterId} onValueChange={setClusterId}>
          <SelectTrigger id="AddRemoteWorkspaceForm-destination">
            <SelectValue placeholder="Choose a destination" />
          </SelectTrigger>
          <SelectContent>
            {destinations.data?.destinations.map((destination) => (
              <SelectItem key={destination.id} value={destination.id}>
                {destination.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {destinations.isPending && (
          <p className="text-label text-muted-foreground">Loading destinations…</p>
        )}
        {destinations.isError && (
          <p
            className="flex items-center gap-1 text-label text-status-failed-foreground"
            role="alert"
          >
            Unable to load destinations.
          </p>
        )}
        {destinations.isSuccess && destinations.data.destinations.length === 0 && (
          <p className="text-label text-muted-foreground">Register a destination in molq first.</p>
        )}
      </div>
      <div className="grid gap-2">
        <Label htmlFor="AddRemoteWorkspaceForm-root">Workspace root</Label>
        <Input
          id="AddRemoteWorkspaceForm-root"
          value={root}
          onChange={(event) => setRoot(event.target.value)}
          placeholder="/scratch/me/molab"
          required
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="remote-workspace-cache">Content cache</Label>
        <Select
          value={cacheMode}
          onValueChange={(value) => setCacheMode(value as WorkspaceTargetCreateRequest.cacheMode)}
        >
          <SelectTrigger id="remote-workspace-cache">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="pinned">Keep until refresh</SelectItem>
            <SelectItem value="strict">Fetch on every read</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </AppDialog>
  );
}
