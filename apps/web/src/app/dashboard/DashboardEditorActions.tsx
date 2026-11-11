/**
 * The Dashboard's editor actions (Figma L01-1, decision 5): New project —
 * secondary while runs are going — then ⋯ with New project…, Open runs, Open
 * projects and Sync now.
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@molcrafts/ui";
import { MoreHorizontal } from "lucide-react";
import type { JSX } from "react";
import { usePermissions } from "@/app/auth";
import { DialogButton } from "@/components/dialog/AppDialog";
import { WorkbenchIconAction } from "@/components/workbench";

export interface DashboardEditorActionsProps {
  /** Runs are going: New project steps back to secondary. */
  active: boolean;
  syncing: boolean;
  onNewProject: () => void;
  onOpenRuns: () => void;
  onOpenProjects: () => void;
  onSync: () => void;
}

export function DashboardEditorActions({
  active,
  syncing,
  onNewProject,
  onOpenRuns,
  onOpenProjects,
  onSync,
}: DashboardEditorActionsProps): JSX.Element {
  const { writeDeniedReason } = usePermissions();
  const canWrite = !writeDeniedReason;
  return (
    <div className="flex items-center gap-1">
      <DialogButton
        size="chrome"
        kind={active ? "secondary" : "primary"}
        disabled={!canWrite}
        title={writeDeniedReason ?? undefined}
        onClick={onNewProject}
      >
        New project
      </DialogButton>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <WorkbenchIconAction label="More actions">
            <MoreHorizontal className="size-icon" />
          </WorkbenchIconAction>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuItem disabled={!canWrite} onSelect={onNewProject}>
            New project…
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={onOpenRuns}>Open runs</DropdownMenuItem>
          <DropdownMenuItem onSelect={onOpenProjects}>Open projects</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled={syncing} onSelect={onSync}>
            {syncing ? "Syncing…" : "Sync now"}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
