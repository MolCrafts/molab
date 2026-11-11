/**
 * Import a file already in the served workspace as a project asset (L08) —
 * the same verb as `molab asset import` (`POST /projects/{id}/assets`).
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
import { useQueryClient } from "@tanstack/react-query";
import { type JSX, useEffect, useState } from "react";
import { assetsApi } from "@/api";
import { projectKeys } from "@/app/state/entityQueries";
import type { ProjectSummary } from "@/app/types";
import { AppDialog } from "@/components/dialog/AppDialog";
import { toast } from "@/components/ui/toast";

interface ImportAssetDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projects: readonly ProjectSummary[];
  /** The project to preselect. */
  projectId?: string;
  onImported: () => void;
}

/** A workspace-relative path: no leading slash, no `..`. */
export const importPathProblem = (path: string): string | null => {
  const trimmed = path.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("/")) return "Use a path inside the workspace, without a leading /.";
  if (trimmed.split("/").includes("..")) return "The path cannot leave the workspace (..).";
  return null;
};

const baseName = (path: string): string => path.trim().split("/").filter(Boolean).at(-1) ?? "";

export const ImportAssetDialog = ({
  open,
  onOpenChange,
  projects,
  projectId: initialProjectId,
  onImported,
}: ImportAssetDialogProps): JSX.Element => {
  const queryClient = useQueryClient();
  const [projectId, setProjectId] = useState(initialProjectId ?? projects[0]?.id ?? "");
  const [path, setPath] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setProjectId(initialProjectId ?? projects[0]?.id ?? "");
      setPath("");
      setTitle("");
      setError(null);
    }
  }, [open, initialProjectId, projects]);

  const problem = importPathProblem(path);
  const name = title.trim() || baseName(path);

  const submit = async (): Promise<void> => {
    if (problem || !projectId || !path.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await assetsApi.importFile(projectId, name, path.trim());
      await queryClient.invalidateQueries({ queryKey: projectKeys.assets(projectId) });
      toast(`Imported ${name}`);
      onOpenChange(false);
      onImported();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not import the file");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Import asset"
      size="form"
      primaryLabel="Import asset"
      busyLabel="Importing…"
      busy={busy}
      primaryDisabled={!projectId || !path.trim() || Boolean(problem)}
      onPrimary={submit}
      error={error ?? problem}
    >
      <div className="grid gap-3">
        <div className="grid gap-2">
          <Label htmlFor="import-project">Project</Label>
          <Select value={projectId} onValueChange={setProjectId}>
            <SelectTrigger id="import-project">
              <SelectValue placeholder="Choose a project" />
            </SelectTrigger>
            <SelectContent>
              {projects.map((project) => (
                <SelectItem key={project.id} value={project.id}>
                  {project.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="import-path">File in the workspace</Label>
          <Input
            id="import-path"
            value={path}
            placeholder="data/ligands.csv"
            className="font-mono"
            onChange={(event) => setPath(event.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="import-title">Title</Label>
          <Input
            id="import-title"
            value={title}
            placeholder={baseName(path) || "The file name"}
            onChange={(event) => setTitle(event.target.value)}
          />
        </div>
      </div>
    </AppDialog>
  );
};
