/**
 * Constitution-aware `cn` — copied from molexp web (not imported from molvis).
 */
import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

const FONT_SIZES = [
  "micro",
  "label",
  "meta",
  "body",
  "body-lg",
  "title",
  "heading",
  "display",
] as const;

const RADII = ["control", "panel", "overlay", "checkbox"] as const;

const SPACING = [
  "control",
  "control-comfortable",
  "control-compact",
  "toolbar",
  "toolbar-compact",
  "statusbar",
  "touch-target",
  "menu",
  "menu-compact",
  "dialog-sm",
  "dialog-md",
  "dialog-lg",
  "dialog-wide",
  "dialog-tall",
  "dialog-scroll",
  "dialog-scroll-compact",
  "dialog-viewport",
  "dialog-viewport-tall",
  "dialog-sidebar",
  "overlay-viewport",
  "panel-sm",
  "panel-md",
  "panel-lg",
  "field-label",
  "inspector",
  "command-offset",
  "canvas-min",
] as const;

const CONTAINERS = ["content", "prose-measure", "rail"] as const;

const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: [...FONT_SIZES] }],
      rounded: [{ rounded: [...RADII] }],
      h: [{ h: [...SPACING] }],
      "min-h": [{ "min-h": [...SPACING] }],
      "max-h": [{ "max-h": [...SPACING] }],
      w: [{ w: [...SPACING, ...CONTAINERS] }],
      "min-w": [{ "min-w": [...SPACING, ...CONTAINERS] }],
      "max-w": [{ "max-w": [...SPACING, ...CONTAINERS] }],
      size: [{ size: [...SPACING] }],
    },
  },
});

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
