/** An asset kind's icon on its tinted tile (L08). */

import type { JSX } from "react";
import { cn } from "@/lib/utils";
import { ASSET_KIND_META, type AssetKind } from "./assetKinds";

const TILE_SIZE = {
  sm: "size-6 rounded-sm [&>svg]:size-icon-sm",
  md: "size-8 rounded-md [&>svg]:size-icon",
  lg: "size-12 rounded-lg [&>svg]:size-6",
} as const;

export const AssetTile = ({
  kind,
  size = "md",
}: {
  kind: AssetKind;
  size?: keyof typeof TILE_SIZE;
}): JSX.Element => {
  const meta = ASSET_KIND_META[kind];
  const Icon = meta.icon;
  return (
    <span
      className={cn("flex flex-none items-center justify-center", meta.ground, TILE_SIZE[size])}
    >
      <Icon aria-hidden className={meta.ink} />
    </span>
  );
};

/** The kind icon alone, in its ink (rows, tabs, the side bar). */
export const AssetKindIcon = ({
  kind,
  className,
}: {
  kind: AssetKind;
  className?: string;
}): JSX.Element => {
  const meta = ASSET_KIND_META[kind];
  const Icon = meta.icon;
  return (
    <Icon aria-label={meta.label} className={cn("size-icon-sm flex-none", meta.ink, className)} />
  );
};
