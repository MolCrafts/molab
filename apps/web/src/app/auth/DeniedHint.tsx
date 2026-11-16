/**
 * Wrap a control that is disabled due to missing permission so hover still
 * explains why (native `title` on disabled buttons is unreliable).
 */

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@molcrafts/ui";
import type { ReactNode } from "react";

export function DeniedHint({
  reason,
  children,
}: {
  reason: string | null | undefined;
  children: ReactNode;
}): JSX.Element {
  if (!reason) {
    return <>{children}</>;
  }
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex max-w-full">{children}</span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-xs text-pretty">
          {reason}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
