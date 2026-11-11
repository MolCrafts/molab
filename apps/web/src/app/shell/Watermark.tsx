/**
 * Editor watermark (L00): what the editor shows with nothing open — the
 * product mark and the few keys that get you somewhere. Replaces the old
 * per-section "No … selected" placeholders.
 */

import { Kbd } from "@molcrafts/ui";
import type { JSX } from "react";
import { SHORTCUTS } from "./keys";
import { ProductMark } from "./ProductMark";

const HINTS: ReadonlyArray<{ label: string; keys: () => string }> = [
  { label: "Go to", keys: SHORTCUTS.goTo },
  { label: "Show commands", keys: SHORTCUTS.commands },
  { label: "Move between regions", keys: SHORTCUTS.regions },
  { label: "Toggle side bar", keys: SHORTCUTS.sideBar },
];

export const Watermark = (): JSX.Element => (
  <div
    className="flex h-full items-center justify-center bg-background"
    data-testid="editor-watermark"
  >
    <div className="flex flex-col items-center gap-6">
      <ProductMark className="size-16 text-border" strokeWidth={1} />
      <dl className="grid grid-cols-2 items-center gap-x-3 gap-y-2 text-label">
        {HINTS.map((hint) => (
          <div key={hint.label} className="contents">
            <dt className="text-right text-muted-foreground">{hint.label}</dt>
            <dd>
              <Kbd>{hint.keys()}</Kbd>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  </div>
);
