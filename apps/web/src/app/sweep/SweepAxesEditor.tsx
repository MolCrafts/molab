/**
 * The axis rows of a sweep. The dialog owns the draft; this only edits it.
 */

import { Input, Label } from "@molcrafts/ui";
import { Plus, X } from "lucide-react";
import type { JSX } from "react";
import { WorkbenchAction } from "@/components/workbench";
import { type AxisDraft, axisDraft } from "./grid";

export interface SweepAxesEditorProps {
  drafts: readonly AxisDraft[];
  disabled?: boolean;
  onChange: (drafts: AxisDraft[]) => void;
}

export const SweepAxesEditor = ({
  drafts,
  disabled = false,
  onChange,
}: SweepAxesEditorProps): JSX.Element => {
  const update = (id: string, patch: Partial<AxisDraft>): void => {
    onChange(drafts.map((draft) => (draft.id === id ? { ...draft, ...patch } : draft)));
  };

  return (
    <div className="grid gap-3">
      {drafts.map((draft, index) => (
        <fieldset key={draft.id} className="grid gap-2 border border-border p-3">
          <legend className="px-1 text-micro text-muted-foreground">Axis {index + 1}</legend>
          <div className="grid gap-2 sm:grid-cols-[minmax(0,8rem)_minmax(0,1fr)_auto] sm:items-end">
            <div className="grid gap-1">
              <Label htmlFor={`sweep-name-${draft.id}`}>Name</Label>
              <Input
                id={`sweep-name-${draft.id}`}
                value={draft.name}
                disabled={disabled}
                onChange={(event) => update(draft.id, { name: event.target.value })}
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor={`sweep-values-${draft.id}`}>Values</Label>
              <Input
                id={`sweep-values-${draft.id}`}
                value={draft.valuesText}
                disabled={disabled}
                placeholder="0.1, 0.2, 0.3"
                onChange={(event) => update(draft.id, { valuesText: event.target.value })}
              />
            </div>
            <WorkbenchAction
              icon={<X aria-hidden />}
              kind="ghost"
              size="compact"
              type="button"
              disabled={disabled || drafts.length === 1}
              onClick={() => onChange(drafts.filter((item) => item.id !== draft.id))}
            >
              Remove
            </WorkbenchAction>
          </div>
        </fieldset>
      ))}
      <WorkbenchAction
        icon={<Plus aria-hidden />}
        kind="ghost"
        size="compact"
        type="button"
        disabled={disabled}
        onClick={() =>
          onChange([...drafts, axisDraft(`axis-${drafts.length}-${drafts.at(-1)?.id ?? "0"}`)])
        }
      >
        Add axis
      </WorkbenchAction>
    </div>
  );
};
