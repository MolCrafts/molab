/** A status glyph in its colour, from the one status vocabulary (DS v1.4 §3). */

import type { JSX } from "react";
import { statusSpec, TONE_TEXT } from "@/app/status/vocabulary";
import { cn } from "@/lib/utils";

interface StatusIconProps {
  status: string | null | undefined;
  className?: string;
  /** Overrides the vocabulary's word for assistive tech. */
  label?: string;
}

export const StatusIcon = ({ status, className, label }: StatusIconProps): JSX.Element => {
  const spec = statusSpec(status);
  const Icon = spec.glyph;
  return (
    <Icon
      aria-label={label ?? spec.word}
      role="img"
      className={cn(
        "size-icon-sm flex-none",
        TONE_TEXT[spec.tone],
        spec.spin && "mol-motion-progress-spin",
        className,
      )}
    />
  );
};
