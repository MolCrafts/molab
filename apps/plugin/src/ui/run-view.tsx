/**
 * `<RunView>` — the one frame every run plugin renders (L14):
 *
 *   files (left, full height) | the view (centre) | style (right, closable)
 *
 * The view's own buttons (`actions`, e.g. a Group by menu) sit at its top
 * right, beside an optional `header` (a legend). There are no plugin tabs,
 * toggle rows, summaries or headers. The run's attempt is the host's (the
 * chip at the right of the run's views); a view reads it with
 * `useRunAttempt()` and reads files with `useAttemptText / useAttemptBlob`.
 */

import { createContext, type JSX, type ReactNode, useContext, useState } from "react";
import type { AttemptRead, RunAttempt, RunViewHost } from "../contract";
import { cn } from "../utils";
import {
  IconPanelRight,
  IconX,
  RunViewChoice,
  RunViewFacts,
  RunViewFiles,
  RunViewGrid,
  RunViewIconButton,
  RunViewMenu,
  RunViewPanel,
  RunViewState,
  type RunViewStateSpec,
  RunViewStyleGroup,
  RunViewStyleRow,
  RunViewSwitch,
} from "./run-view-parts";

const RunViewHostContext = createContext<RunViewHost | null>(null);

/** The host provides this around every run view. */
export const RunViewHostProvider = RunViewHostContext.Provider;

const useHost = (): RunViewHost => {
  const host = useContext(RunViewHostContext);
  if (!host) throw new Error("Run view hooks need the run page (RunViewHostProvider).");
  return host;
};

/** The attempt this view shows — the run page's, chosen by the host. */
export const useRunAttempt = (): RunAttempt => useHost().attempt;

/** The text of an attempt-relative file (null: nothing to read). */
export const useAttemptText = (path: string | null): AttemptRead<string> =>
  useHost().useAttemptText(path);

/** An object URL for an attempt-relative file (images, binary structures). */
export const useAttemptBlob = (path: string | null): AttemptRead<string> =>
  useHost().useAttemptBlob(path);

/** Links out of a view: open a file in the editor, open the run's Logs. */
export const useRunLinks = (): Pick<RunViewHost, "openFile" | "openLogs"> => {
  const { openFile, openLogs } = useHost();
  return { openFile, openLogs };
};

export interface RunViewProps {
  /** `<RunView.Files>`: what the view reads (left). */
  files?: ReactNode;
  /** Left of the view's top row (a legend). */
  header?: ReactNode;
  /** Right of the view's top row: the view's own buttons. */
  actions?: ReactNode;
  /** `<RunView.Style>` content: grouped style settings (right, closable). */
  style?: ReactNode;
  /** Loading / empty / error replace the view; files and style stay. */
  state?: RunViewStateSpec | null;
  /** Start with the style panel closed. */
  styleClosed?: boolean;
  children?: ReactNode;
}

const RunViewRoot = ({
  files,
  header,
  actions,
  style,
  state,
  styleClosed = false,
  children,
}: RunViewProps): JSX.Element => {
  // Phones start with the style sheet closed; it opens over the view.
  const [styleOpen, setStyleOpen] = useState(
    () =>
      !styleClosed &&
      !(typeof window !== "undefined" && window.matchMedia?.("(max-width: 767px)").matches),
  );
  const showTopRow = Boolean(header || actions || (style && !styleOpen));
  return (
    <div className="relative flex h-full min-h-0 bg-background max-md:flex-col">
      {files}
      <div className="flex min-w-0 flex-1 flex-col">
        {showTopRow ? (
          <div className="flex min-h-8 flex-none items-center gap-3 px-6 pt-3 max-md:px-3">
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">{header}</div>
            {actions}
            {style && !styleOpen ? (
              <RunViewIconButton label="Show style" onClick={() => setStyleOpen(true)}>
                <IconPanelRight />
              </RunViewIconButton>
            ) : null}
          </div>
        ) : null}
        <div
          className={cn(
            "min-h-0 flex-1 overflow-auto",
            showTopRow ? "px-6 pt-2 pb-6 max-md:px-3" : "",
          )}
        >
          {state ? <RunViewState state={state} /> : children}
        </div>
      </div>
      {style && styleOpen ? (
        <aside
          aria-label="Style"
          className={cn(
            "flex min-h-0 w-66 flex-none flex-col border-l border-border bg-background",
            "max-md:absolute max-md:inset-x-0 max-md:bottom-0 max-md:z-20 max-md:max-h-[70%] max-md:w-full max-md:border-t max-md:border-l-0 max-md:shadow-overlay",
          )}
        >
          <div className="flex h-8 flex-none items-center border-b border-border pr-1 pl-3">
            <span className="flex-1 text-micro font-semibold uppercase tracking-wide text-muted-foreground">
              Style
            </span>
            <RunViewIconButton label="Hide style" onClick={() => setStyleOpen(false)}>
              <IconX />
            </RunViewIconButton>
          </div>
          <div className="min-h-0 flex-1 overflow-auto pb-3">{style}</div>
        </aside>
      ) : null}
    </div>
  );
};

/** `<RunView>` and its parts: `RunView.Files`, `.Menu`, `.StyleGroup`, `.StyleRow`, `.Choice`, `.Switch`, `.Panel`, `.Grid`, `.Facts`. */
export const RunView = Object.assign(RunViewRoot, {
  Files: RunViewFiles,
  Menu: RunViewMenu,
  StyleGroup: RunViewStyleGroup,
  StyleRow: RunViewStyleRow,
  Choice: RunViewChoice,
  Switch: RunViewSwitch,
  Panel: RunViewPanel,
  Grid: RunViewGrid,
  Facts: RunViewFacts,
  IconButton: RunViewIconButton,
});

export type { RunViewFileItem, RunViewStateSpec } from "./run-view-parts";
