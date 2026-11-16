/**
 * The Workflow view's actions, as VS Code editor-title actions in the tab row
 * (retrofit R7 / R8: there is no toolbar row): icons only — read only (a lock,
 * for a code workflow), Save (only while edited; ⌘S is the way), Graph |
 * Source (List | Graph on a phone), then undo · redo and zoom − % + · fit while
 * the graph is shown. They sit before the experiment's own actions.
 */

import {
  FileCode,
  ListOrdered,
  Lock,
  Maximize2,
  Minus,
  Plus,
  Redo2,
  Save,
  Undo2,
  Workflow,
} from "lucide-react";
import type { JSX } from "react";
import { EditorActions } from "@/app/shell/editorActions";
import { WorkbenchIconAction, WorkbenchToggleAction } from "@/components/workbench";
import type { CanvasTools } from "./flowgram-canvas";

export type WorkflowMode = "list" | "graph" | "source";

const MODES = [
  { value: "graph", label: "Graph", icon: Workflow },
  { value: "source", label: "Source", icon: FileCode },
] as const;
/** Phones read the tasks as a list first (L06-8). */
const PHONE_MODES = [
  { value: "list", label: "Task list", icon: ListOrdered },
  { value: "graph", label: "Graph", icon: Workflow },
] as const;

const Rule = (): JSX.Element => <span aria-hidden className="mx-1 h-4 w-px bg-border" />;

export interface WorkflowActionsProps {
  readOnly: boolean;
  phone: boolean;
  mode: WorkflowMode;
  onModeChange: (mode: WorkflowMode) => void;
  /** Live canvas tools while the graph is shown; null otherwise. */
  tools: CanvasTools | null;
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
}

export const WorkflowActions = ({
  readOnly,
  phone,
  mode,
  onModeChange,
  tools,
  dirty,
  saving,
  onSave,
}: WorkflowActionsProps): JSX.Element => (
  <EditorActions>
    {/* `order-first`: the view's actions come before the experiment's (Resume, ⋯). */}
    <div
      role="toolbar"
      aria-label="Workflow"
      className="order-first flex items-center gap-hairline"
    >
      {readOnly ? (
        <span
          role="img"
          aria-label="Read only — defined in code"
          title="Read only — defined in code"
          className="flex size-shell-action items-center justify-center text-muted-foreground"
        >
          <Lock aria-hidden className="size-icon-sm" />
        </span>
      ) : null}
      {dirty ? (
        <WorkbenchIconAction
          label={saving ? "Saving…" : "Save"}
          shortcut="⌘S"
          disabled={saving}
          className="text-accent"
          onClick={onSave}
        >
          <Save aria-hidden />
        </WorkbenchIconAction>
      ) : null}
      {(phone ? PHONE_MODES : MODES).map((choice) => (
        <WorkbenchToggleAction
          key={choice.value}
          label={choice.label}
          pressed={mode === choice.value}
          onClick={() => onModeChange(choice.value)}
        >
          <choice.icon aria-hidden className="size-icon" />
        </WorkbenchToggleAction>
      ))}
      {tools && !phone ? (
        <>
          <Rule />
          {tools.editable ? (
            <>
              <WorkbenchIconAction label="Undo" shortcut="⌘Z" onClick={tools.undo}>
                <Undo2 aria-hidden />
              </WorkbenchIconAction>
              <WorkbenchIconAction label="Redo" shortcut="⇧⌘Z" onClick={tools.redo}>
                <Redo2 aria-hidden />
              </WorkbenchIconAction>
              <Rule />
            </>
          ) : null}
          <WorkbenchIconAction label="Zoom out" onClick={tools.zoomOut}>
            <Minus aria-hidden />
          </WorkbenchIconAction>
          <span
            aria-live="polite"
            className="min-w-[4ch] text-center font-mono text-micro tabular-nums text-muted-foreground"
          >
            {tools.zoomPercent}%
          </span>
          <WorkbenchIconAction label="Zoom in" onClick={tools.zoomIn}>
            <Plus aria-hidden />
          </WorkbenchIconAction>
          <WorkbenchIconAction label="Fit to view" onClick={tools.fit}>
            <Maximize2 aria-hidden />
          </WorkbenchIconAction>
          <Rule />
        </>
      ) : (
        <Rule />
      )}
    </div>
  </EditorActions>
);
