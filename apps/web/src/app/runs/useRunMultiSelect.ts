import { useCallback, useMemo, useState } from "react";

import {
  type ClickModifiers,
  type MultiSelectState,
  nextSelection,
} from "@/app/compare/nextSelection";

export type { ClickModifiers, MultiSelectState };
export { nextSelection };

export interface UseRunMultiSelect {
  /** Whether multi-select mode is active (rows become selectable, nav suppressed). */
  enabled: boolean;
  selected: Set<string>;
  toggleMode: () => void;
  /** Apply a click at `index` with the given keyboard modifiers. */
  selectAt: (index: number, modifiers: ClickModifiers) => void;
  clear: () => void;
}

export const useRunMultiSelect = (orderedIds: string[]): UseRunMultiSelect => {
  const [enabled, setEnabled] = useState(false);
  const [state, setState] = useState<MultiSelectState>(() => ({
    selected: new Set<string>(),
    anchor: null,
  }));

  const selectAt = useCallback(
    (index: number, modifiers: ClickModifiers) => {
      setState((current) => nextSelection(current, index, orderedIds, modifiers));
    },
    [orderedIds],
  );

  const clear = useCallback(() => {
    setState({ selected: new Set<string>(), anchor: null });
  }, []);

  const toggleMode = useCallback(() => {
    setEnabled((value) => !value);
    setState({ selected: new Set<string>(), anchor: null });
  }, []);

  return useMemo(
    () => ({ enabled, selected: state.selected, toggleMode, selectAt, clear }),
    [enabled, state.selected, toggleMode, selectAt, clear],
  );
};
