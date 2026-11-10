import {
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@molcrafts/ui";
import { Plus, X } from "lucide-react";
import type { JSX } from "react";
import { WorkbenchAction } from "@/components/workbench";
import {
  emptyStage,
  emptyTodo,
  MILESTONE_STATUSES,
  type MilestoneDraft,
  type PlanningClass,
  type PlanningDraft,
  TODO_STATUSES,
  type TodoStatus,
} from "./planningModel";

const updateList = <T,>(rows: T[], index: number, patch: Partial<T>): T[] =>
  rows.map((row, i) => (i === index ? { ...row, ...patch } : row));

export const PlanningFields = ({
  cls,
  draft,
  disabled = false,
  onChange,
}: {
  cls: PlanningClass;
  draft: PlanningDraft;
  disabled?: boolean;
  onChange: (draft: PlanningDraft) => void;
}): JSX.Element => {
  if (cls === "Roadmap") {
    return (
      <div className="grid gap-3">
        {draft.stages.map((row, index) => (
          <fieldset key={row.key} className="grid gap-2 border border-border p-3">
            <legend className="px-1 text-label font-medium text-muted-foreground">
              Stage {index + 1}
            </legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-1">
                <Label htmlFor={`stage-id-${index}`}>Id</Label>
                <Input
                  id={`stage-id-${index}`}
                  value={row.id}
                  disabled={disabled}
                  onChange={(event) =>
                    onChange({
                      ...draft,
                      stages: updateList(draft.stages, index, { id: event.target.value }),
                    })
                  }
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor={`stage-title-${index}`}>Title</Label>
                <Input
                  id={`stage-title-${index}`}
                  value={row.title}
                  disabled={disabled}
                  onChange={(event) =>
                    onChange({
                      ...draft,
                      stages: updateList(draft.stages, index, { title: event.target.value }),
                    })
                  }
                />
              </div>
            </div>
            <div className="grid gap-1">
              <Label htmlFor={`stage-experiment-${index}`}>Experiment</Label>
              <Input
                id={`stage-experiment-${index}`}
                value={row.experiment}
                disabled={disabled}
                placeholder="Optional"
                onChange={(event) =>
                  onChange({
                    ...draft,
                    stages: updateList(draft.stages, index, { experiment: event.target.value }),
                  })
                }
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor={`stage-depends-${index}`}>Depends on</Label>
              <Input
                id={`stage-depends-${index}`}
                value={row.depends}
                disabled={disabled}
                placeholder="stage ids, comma-separated"
                onChange={(event) =>
                  onChange({
                    ...draft,
                    stages: updateList(draft.stages, index, { depends: event.target.value }),
                  })
                }
              />
            </div>
            <WorkbenchAction
              icon={<X aria-hidden />}
              kind="ghost"
              size="compact"
              type="button"
              disabled={disabled || draft.stages.length === 1}
              onClick={() =>
                onChange({ ...draft, stages: draft.stages.filter((_, i) => i !== index) })
              }
            >
              Remove stage
            </WorkbenchAction>
          </fieldset>
        ))}
        <WorkbenchAction
          icon={<Plus aria-hidden />}
          kind="ghost"
          size="compact"
          type="button"
          disabled={disabled}
          onClick={() => onChange({ ...draft, stages: [...draft.stages, emptyStage()] })}
        >
          Add stage
        </WorkbenchAction>
      </div>
    );
  }

  if (cls === "Todo") {
    return (
      <div className="grid gap-3">
        {draft.items.map((row, index) => (
          <fieldset key={row.key} className="grid gap-2 border border-border p-3">
            <legend className="px-1 text-label font-medium text-muted-foreground">
              Item {index + 1}
            </legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-1">
                <Label htmlFor={`todo-id-${index}`}>Id</Label>
                <Input
                  id={`todo-id-${index}`}
                  value={row.id}
                  disabled={disabled}
                  onChange={(event) =>
                    onChange({
                      ...draft,
                      items: updateList(draft.items, index, { id: event.target.value }),
                    })
                  }
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor={`todo-title-${index}`}>Title</Label>
                <Input
                  id={`todo-title-${index}`}
                  value={row.title}
                  disabled={disabled}
                  onChange={(event) =>
                    onChange({
                      ...draft,
                      items: updateList(draft.items, index, { title: event.target.value }),
                    })
                  }
                />
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-1">
                <Label htmlFor={`todo-status-${index}`}>Status</Label>
                <Select
                  value={row.status}
                  onValueChange={(value) =>
                    onChange({
                      ...draft,
                      items: updateList(draft.items, index, { status: value as TodoStatus }),
                    })
                  }
                >
                  <SelectTrigger id={`todo-status-${index}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TODO_STATUSES.map((status) => (
                      <SelectItem key={status} value={status}>
                        {status}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1">
                <Label htmlFor={`todo-stage-${index}`}>Stage</Label>
                <Input
                  id={`todo-stage-${index}`}
                  value={row.stage}
                  disabled={disabled}
                  placeholder="Optional"
                  onChange={(event) =>
                    onChange({
                      ...draft,
                      items: updateList(draft.items, index, { stage: event.target.value }),
                    })
                  }
                />
              </div>
            </div>
            <WorkbenchAction
              icon={<X aria-hidden />}
              kind="ghost"
              size="compact"
              type="button"
              disabled={disabled || draft.items.length === 1}
              onClick={() =>
                onChange({ ...draft, items: draft.items.filter((_, i) => i !== index) })
              }
            >
              Remove item
            </WorkbenchAction>
          </fieldset>
        ))}
        <WorkbenchAction
          icon={<Plus aria-hidden />}
          kind="ghost"
          size="compact"
          type="button"
          disabled={disabled}
          onClick={() => onChange({ ...draft, items: [...draft.items, emptyTodo()] })}
        >
          Add item
        </WorkbenchAction>
      </div>
    );
  }

  const milestone: MilestoneDraft = draft.milestone;
  return (
    <div className="grid gap-2">
      <Label htmlFor="milestone-stage">Stage</Label>
      <Input
        id="milestone-stage"
        value={milestone.stage}
        disabled={disabled}
        onChange={(event) =>
          onChange({ ...draft, milestone: { ...milestone, stage: event.target.value } })
        }
      />
      <Label htmlFor="milestone-criterion">Criterion</Label>
      <Input
        id="milestone-criterion"
        value={milestone.criterion}
        disabled={disabled}
        onChange={(event) =>
          onChange({ ...draft, milestone: { ...milestone, criterion: event.target.value } })
        }
      />
      <Label htmlFor="milestone-status">Status</Label>
      <Select
        value={milestone.status}
        onValueChange={(value) =>
          onChange({
            ...draft,
            milestone: { ...milestone, status: value as MilestoneDraft["status"] },
          })
        }
      >
        <SelectTrigger id="milestone-status">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {MILESTONE_STATUSES.map((status) => (
            <SelectItem key={status} value={status}>
              {status}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
};
