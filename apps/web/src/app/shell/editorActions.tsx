/**
 * Editor actions (L00): a page's primary action and ⋯ live at the right end
 * of the editor tab row (VS Code editor actions), not in a header inside the
 * page. The shell owns the slot; a page hands its actions over with
 * `<EditorActions>`. Outside the shell (tests, a page rendered alone) there is
 * no slot and the actions render in place, so nothing is ever lost.
 */

import { createContext, type JSX, type ReactNode, useContext } from "react";
import { createPortal } from "react-dom";

const EditorActionsSlot = createContext<HTMLElement | null>(null);

export const EditorActionsSlotProvider = EditorActionsSlot.Provider;

export const EditorActions = ({ children }: { children: ReactNode }): JSX.Element | null => {
  const slot = useContext(EditorActionsSlot);
  if (!children) return null;
  if (!slot) return <div className="flex flex-none items-center gap-hairline">{children}</div>;
  return createPortal(children, slot);
};
