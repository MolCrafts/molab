/**
 * F6 / ⇧F6 (L00): move focus between the shell's regions in reading order —
 * activity bar → side bar → editor → panel. A region is any element marked
 * `data-shell-region`; a hidden region is simply absent from the cycle.
 */

const ORDER = ["activitybar", "sidebar", "editor", "panel"] as const;

/** Tried in this order: the region's current item first, any control last. */
const FOCUS_PRIORITY = [
  '[role="treeitem"][tabindex="0"]',
  '[role="tab"][aria-selected="true"]',
  '[aria-pressed="true"]',
  'button:not([disabled]):not([tabindex="-1"]), a[href], input, [tabindex="0"]',
] as const;

export const focusShellRegion = (delta: number, root: ParentNode = document): void => {
  const regions = ORDER.flatMap((id) => {
    const element = root.querySelector<HTMLElement>(`[data-shell-region="${id}"]`);
    return element ? [element] : [];
  });
  if (regions.length === 0) return;
  const active = document.activeElement;
  const current = regions.findIndex((region) => active && region.contains(active));
  const start = current < 0 ? (delta > 0 ? -1 : 0) : current;
  const next = regions[(((start + delta) % regions.length) + regions.length) % regions.length];
  if (!next) return;
  const target = FOCUS_PRIORITY.reduce<HTMLElement | null>(
    (found, selector) => found ?? next.querySelector<HTMLElement>(selector),
    null,
  );
  if (target) {
    target.focus();
    return;
  }
  if (!next.hasAttribute("tabindex")) next.tabIndex = -1;
  next.focus();
};
