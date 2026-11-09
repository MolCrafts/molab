/**
 * Modal dialog that registers a compute target — used from Settings and as the
 * inline "+ Add target..." shortcut inside Create Experiment / Create Run flows
 * so users don't have to leave their current task to register a new target.
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
import type { TargetCreateRequest } from "@/api/generated/models/TargetCreateRequest";
import type { TargetResponse } from "@/api/generated/models/TargetResponse";
import { MolqService } from "@/api/generated/services/MolqService";
import { TargetsService } from "@/api/generated/services/TargetsService";
import { AppDialog } from "@/components/dialog/AppDialog";

interface AddTargetDialogProps {
  trigger: ReactNode;
  onCreated?: (target: TargetResponse) => void;
}

export function AddTargetDialog({ trigger, onCreated }: AddTargetDialogProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [clusterId, setClusterId] = useState("");
  const [root, setRoot] = useState("");
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
    setError(null);
  };

  const handleSubmit = async (): Promise<void> => {
    if (!destinations.data || !clusterId) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload: TargetCreateRequest = {
        name: name.trim(),
        scratchRoot: root.trim(),
        registryId: destinations.data.registryId,
        clusterId,
      };
      const created = await TargetsService.createTargetEndpoint(payload);
      changeOpen(false);
      onCreated?.(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add target");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppDialog
      open={open}
      onOpenChange={changeOpen}
      title="Add compute target"
      message="Register a destination for runs. Local targets execute on this machine; remote targets dispatch via SSH and an optional batch scheduler."
      size="form"
      primaryLabel="Add target"
      busyLabel="Adding…"
      busy={submitting}
      primaryDisabled={!clusterId || !destinations.data || !name || !root}
      onPrimary={handleSubmit}
      error={error}
      trigger={trigger}
    >
      <div className="grid gap-2">
        <Label htmlFor="AddTargetForm-name">Name</Label>
        <Input
          id="AddTargetForm-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="AddTargetForm-destination">Destination</Label>
        <Select value={clusterId} onValueChange={setClusterId}>
          <SelectTrigger id="AddTargetForm-destination">
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
        <Label htmlFor="AddTargetForm-root">Scratch root</Label>
        <Input
          id="AddTargetForm-root"
          value={root}
          onChange={(event) => setRoot(event.target.value)}
          placeholder="/scratch/me/molab"
          required
        />
      </div>
    </AppDialog>
  );
}
