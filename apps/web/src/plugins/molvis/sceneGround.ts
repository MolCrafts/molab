/**
 * The scene's ground is the page's: the `--color-background` token, read at
 * runtime (it is an oklch value, and the stage takes `#RRGGBB`), and read
 * again when the theme changes.
 */

import { useMemo } from "react";
import { useUiTheme } from "@/lib/ui-theme";

const GROUND_TOKEN = "--color-background";

/** `#RRGGBB` from three 0–255 channels. */
export const hexFromRgb = (red: number, green: number, blue: number): string =>
  `#${[red, green, blue]
    .map((channel) =>
      Math.round(Math.min(255, Math.max(0, channel)))
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;

/** Any CSS colour as `#RRGGBB`, through a 1×1 canvas; null without a DOM. */
export const cssColourToHex = (colour: string): string | null => {
  if (typeof document === "undefined" || !colour) return null;
  const context = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  context.fillStyle = colour;
  context.fillRect(0, 0, 1, 1);
  const [red = 0, green = 0, blue = 0] = context.getImageData(0, 0, 1, 1).data;
  return hexFromRgb(red, green, blue);
};

const readGround = (): string | null => {
  if (typeof document === "undefined") return null;
  const probe = document.createElement("span");
  probe.style.display = "none";
  probe.style.color = `var(${GROUND_TOKEN})`;
  document.documentElement.append(probe);
  const resolved = getComputedStyle(probe).color;
  probe.remove();
  return cssColourToHex(resolved);
};

/** The page ground as `#RRGGBB`, following the light / dark theme. */
export const useSceneGround = (): string | null => {
  const theme = useUiTheme();
  return useMemo(() => {
    void theme;
    return readGround();
  }, [theme]);
};
