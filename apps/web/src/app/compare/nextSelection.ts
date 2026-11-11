/**
 * Range/incremental multi-selection reducer.
 *
 * Shift-range / ctrl-meta-toggle is a pure function so it is testable under
 * the node environment, independent of React. The bag lives in `compareSet`;
 * this only answers "which visible keys did the click name".
 */

export interface MultiSelectState {
  selected: Set<string>;
  /** Index of the last plain/ctrl click — origin for a subsequent shift range. */
  anchor: number | null;
}

export interface ClickModifiers {
  /** shiftKey — select the inclusive range from the anchor. */
  shift: boolean;
  /** metaKey || ctrlKey — toggle the single row, preserving the rest. */
  meta: boolean;
}

/**
 * Pure selection transition:
 *  - shift (with an anchor) → add the inclusive index range [anchor, click] to
 *    the current selection, anchor unchanged.
 *  - meta/ctrl → toggle just the clicked id, anchor moves to the click.
 *  - plain → select only the clicked id, anchor moves to the click.
 */
export const nextSelection = (
  state: MultiSelectState,
  clickIndex: number,
  orderedIds: string[],
  modifiers: ClickModifiers,
): MultiSelectState => {
  const id = orderedIds[clickIndex];
  if (id === undefined) return state;

  if (modifiers.shift && state.anchor !== null) {
    const [lo, hi] =
      state.anchor <= clickIndex ? [state.anchor, clickIndex] : [clickIndex, state.anchor];
    const selected = new Set(state.selected);
    for (let i = lo; i <= hi; i += 1) {
      const ranged = orderedIds[i];
      if (ranged !== undefined) selected.add(ranged);
    }
    return { selected, anchor: state.anchor };
  }

  if (modifiers.meta) {
    const selected = new Set(state.selected);
    if (selected.has(id)) {
      selected.delete(id);
    } else {
      selected.add(id);
    }
    return { selected, anchor: clickIndex };
  }

  return { selected: new Set([id]), anchor: clickIndex };
};
