/**
 * `<molab-run-ref ref=… label=…>` (L10): one `molab:` reference — or several,
 * `refs="a b c"` — as chips in a row. A click previews, a double-click opens.
 */

import { Link2 } from "lucide-react";
import type { JSX } from "react";
import type { DocComponentProps, DocComponentSpec } from "../context";
import { ComponentNotice } from "../frame";
import { RefChip } from "../RefChip";

const NAME = "molab-run-ref";

const refsOf = (attrs: Readonly<Record<string, string>>): string[] =>
  [attrs.ref ?? "", ...(attrs.refs ?? "").split(/\s+/)].map((ref) => ref.trim()).filter(Boolean);

export const RunRef = ({ attrs }: DocComponentProps): JSX.Element => {
  const refs = refsOf(attrs);
  if (refs.length === 0) {
    return <ComponentNotice name={NAME}>Needs a ref=molab:… attribute.</ComponentNotice>;
  }
  // A label names a single chip; on a row of several it would name them all alike.
  const label = refs.length === 1 ? attrs.label : undefined;
  return (
    <div className="not-prose flex flex-wrap items-center gap-2">
      {refs.map((ref, index) => (
        // A ref may repeat on purpose; its position keeps the keys distinct.
        // biome-ignore lint/suspicious/noArrayIndexKey: the list is the attribute as written.
        <RefChip key={`${ref}:${index}`} refText={ref}>
          {label || undefined}
        </RefChip>
      ))}
    </div>
  );
};

export const runRefSpec: DocComponentSpec = {
  name: NAME,
  label: "Run reference",
  description: "A run, attempt, experiment or asset by its molab: ref — a click previews it",
  keywords: ["ref", "run", "link", "chip", "experiment", "asset"],
  icon: Link2,
  template: { ref: "molab:run/" },
  Component: RunRef,
};
