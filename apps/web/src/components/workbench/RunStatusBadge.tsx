/**
 * Product surface for run / execution status: the vocabulary's word and colour
 * (DS v1.4 §3). Domain prop only — shadcn Badge API stays inside StatusBadge.
 */

import type { JSX } from "react";

import { StatusBadge, type StatusBadgeSize } from "@/app/components/entity";
import { statusWord } from "@/app/status/vocabulary";

export interface RunStatusBadgeProps {
  status: string | null | undefined;
  size?: StatusBadgeSize;
  dot?: boolean;
  showLabel?: boolean;
}

export const RunStatusBadge = ({
  status,
  size = "sm",
  dot = true,
  showLabel = true,
}: RunStatusBadgeProps): JSX.Element | null => (
  <StatusBadge
    status={status ?? "pending"}
    word={statusWord(status ?? "pending")}
    size={size}
    dot={dot}
    showLabel={showLabel}
  />
);
