/**
 * Product mark. One hexagon, so it does not read as the stacked squares of
 * the project glyph (Blocks) or the workspace folder.
 */

import { Hexagon } from "lucide-react";
import type { JSX } from "react";

export const ProductMark = ({
  className,
  strokeWidth,
}: {
  className?: string;
  strokeWidth?: number;
}): JSX.Element => <Hexagon aria-hidden className={className} strokeWidth={strokeWidth} />;
