/** Register a semantic remote workspace using an existing molq destination. */
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
import { Check, X } from "lucide-react";
import { useState } from "react";
import { WorkspaceTargetCreateRequest } from "@/api/generated/models/WorkspaceTargetCreateRequest";
import type { WorkspaceTargetResponse } from "@/api/generated/models/WorkspaceTargetResponse";
import { MolqService } from "@/api/generated/services/MolqService";
import { WorkspaceService } from "@/api/generated/services/WorkspaceService";
import { WorkbenchAction } from "@/components/workbench";

interface AddRemoteWorkspaceFormProps {
  onCreated?: (target: WorkspaceTargetResponse) => void;
  onCancel?: () => void;
  variant?: "card" | "plain";
}

export function AddRemoteWorkspaceForm({
  onCreated,
  onCancel,
  variant = "plain",
}: AddRemoteWorkspaceFormProps): JSX.Element {
  const [name, setName] = useState("");
  const [clusterId, setClusterId] = useState("");
  const [root, setRoot] = useState("");
  const [cacheMode, setCacheMode] = useState(WorkspaceTargetCreateRequest.cacheMode.PINNED);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const destinations = useQuery({
    queryKey: ["molq", "destinations"],
    queryFn: () => MolqService.listDestinations(),
  });

  const handleSubmit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
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
      setName("");
      setRoot("");
      onCreated?.(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add remote workspace");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className={
        variant === "card" ? "self-start space-y-3 border-t border-border/60 pt-4" : "space-y-3"
      }
    >
      <div className="space-y-1">
        <Label htmlFor="AddRemoteWorkspaceForm-name">Name</Label>
        <Input
          id="AddRemoteWorkspaceForm-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
        />
      </div>
      <div className="space-y-1">
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
          <p role="alert" className="text-label text-status-failed-foreground">
            Unable to load destinations.
          </p>
        )}
        {destinations.isSuccess && destinations.data.destinations.length === 0 && (
          <p className="text-label text-muted-foreground">Register a destination in molq first.</p>
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="AddRemoteWorkspaceForm-root">Workspace root</Label>
        <Input
          id="AddRemoteWorkspaceForm-root"
          value={root}
          onChange={(event) => setRoot(event.target.value)}
          placeholder="/scratch/me/molab"
          required
        />
      </div>
      <div className="space-y-1">
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
      {error && (
        <p role="alert" className="text-body-lg text-status-failed-foreground">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        {onCancel && (
          <WorkbenchAction
            icon={<X aria-hidden />}
            kind="ghost"
            size="default"
            type="button"
            onClick={onCancel}
          >
            Cancel
          </WorkbenchAction>
        )}
        <WorkbenchAction
          icon={<Check aria-hidden />}
          kind="primary"
          size="default"
          type="submit"
          disabled={submitting || !clusterId || !destinations.data}
        >
          {submitting ? "Adding…" : "Add remote workspace"}
        </WorkbenchAction>
      </div>
    </form>
  );
}
