/**
 * First-class workspace activity timeline (workspace-activity-page).
 *
 * Full-center view of run lifecycle, derived from the workspace snapshot.
 * Runs dashboard keeps its compact feed panel; this is the discoverable home.
 */

import { Activity } from "lucide-react";
import type { JSX } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { EntityHeader } from "@/app/components/entity";
import { runPath } from "@/app/entities/paths";
import { eventTypeFilterLabel, WORKSPACE_EVENT_TYPES } from "@/app/runs/activityFeed";
import { WorkspaceActivityFeed } from "@/app/runs/WorkspaceActivityFeed";
import type { WorkspaceSnapshot } from "@/app/types";
import { WorkbenchAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

interface ActivityPageProps {
  snapshot: WorkspaceSnapshot;
}

export const ActivityPage = ({ snapshot }: ActivityPageProps): JSX.Element => {
  const navigate = useNavigate();
  const [eventType, setEventType] = useState<string | null>(null);

  const selectRunById = (runId: string): void => {
    const run = snapshot.runs.find((r) => r.id === runId);
    if (!run) return;
    navigate(runPath(run.projectId, run.experimentId, run.id));
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <EntityHeader icon={Activity} title="Activity" />
      <div className="flex flex-wrap gap-1 border-b border-border/70 px-3 py-2">
        <WorkbenchAction
          kind="ghost"
          size="content"
          type="button"
          className={cn(
            "rounded-control px-2 py-1 text-micro",
            eventType === null && "bg-muted font-medium text-foreground",
          )}
          onClick={() => setEventType(null)}
        >
          All
        </WorkbenchAction>
        {WORKSPACE_EVENT_TYPES.map((type) => (
          <WorkbenchAction
            key={type}
            kind="ghost"
            size="content"
            type="button"
            className={cn(
              "rounded-control px-2 py-1 text-micro",
              eventType === type && "bg-muted font-medium text-foreground",
            )}
            onClick={() => setEventType(type)}
          >
            {eventTypeFilterLabel(type)}
          </WorkbenchAction>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-2 py-2">
        <WorkspaceActivityFeed
          runs={snapshot.runs}
          onSelectRun={selectRunById}
          max={50}
          eventType={eventType}
        />
      </div>
    </div>
  );
};
