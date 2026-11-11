/**
 * What "/" inserts on a knowledge page (L10), beyond Crepe's own text blocks:
 * every `<molab-…>` component (as a leaf directive) and the MkDocs blocks
 * (admonitions, content tabs).
 */

import {
  CircleAlert,
  CircleCheck,
  CircleX,
  FileText,
  Info,
  Lightbulb,
  type LucideIcon,
  PanelTop,
  Pencil,
} from "lucide-react";
import { formatComponent } from "./blocks";
import { DOC_COMPONENTS } from "./registry";

export interface SlashBlock {
  key: string;
  label: string;
  icon: LucideIcon;
  /** The block's markdown (no surrounding blank lines). */
  markdown: () => string;
}

const admonition = (type: string, title: string, icon: LucideIcon): SlashBlock => ({
  key: `admonition-${type}`,
  label: title,
  icon,
  markdown: () => `!!! ${type} "${title}"\n    Write here.`,
});

export const SLASH_BLOCKS: readonly SlashBlock[] = [
  ...DOC_COMPONENTS.map(
    (spec): SlashBlock => ({
      key: spec.name,
      label: spec.label,
      icon: spec.icon,
      markdown: () => formatComponent(spec.name, { ...spec.template }),
    }),
  ),
  admonition("note", "Note", Pencil),
  admonition("abstract", "Abstract", FileText),
  admonition("info", "Info", Info),
  admonition("tip", "Tip", Lightbulb),
  admonition("success", "Success", CircleCheck),
  admonition("warning", "Warning", CircleAlert),
  admonition("failure", "Failure", CircleX),
  {
    key: "tabs",
    label: "Tabs",
    icon: PanelTop,
    markdown: () => '=== "First"\n\n    Write here.\n\n=== "Second"\n\n    Write here.',
  },
];
