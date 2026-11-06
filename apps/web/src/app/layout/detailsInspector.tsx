import { PanelRight } from "lucide-react";
import { createContext, useContext, useMemo } from "react";
import type { Selection, SemanticObjectType } from "@/app/types";
import { WorkbenchIconAction } from "@/components/workbench";

/** Object types whose opaque coordinates live in the right inspector. */
const DETAILS_OBJECT_TYPES = new Set<SemanticObjectType>([
  "project",
  "experiment",
  "run",
  "asset",
  "workspace-file",
]);

export const selectionHasDetails = (selection: Selection | null): boolean =>
  selection != null && DETAILS_OBJECT_TYPES.has(selection.objectType);

interface DetailsInspectorValue {
  open: boolean;
  available: boolean;
  toggle: () => void;
}

const DetailsInspectorContext = createContext<DetailsInspectorValue | null>(null);

export const DetailsInspectorProvider = DetailsInspectorContext.Provider;

export const useDetailsInspectorValue = (
  open: boolean,
  available: boolean,
  toggle: () => void,
): DetailsInspectorValue => useMemo(() => ({ open, available, toggle }), [open, available, toggle]);

/** Opens the right inspector. Hidden when this page has no detail record. */
export const DetailsInspectorButton = (): JSX.Element | null => {
  const details = useContext(DetailsInspectorContext);
  if (!details?.available) return null;
  return (
    <WorkbenchIconAction
      label={details.open ? "Hide details" : "Details"}
      aria-pressed={details.open}
      onClick={details.toggle}
    >
      <PanelRight aria-hidden />
    </WorkbenchIconAction>
  );
};
