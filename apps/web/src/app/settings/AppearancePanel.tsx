/** Settings › Appearance (L11): Color theme and Text size, each a setting. */

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@molcrafts/ui";
import type { JSX } from "react";
import { SettingItem } from "@/components/settings";
import { setTextScale, TEXT_SCALES, useTextScale } from "@/lib/ui-scale";
import { setUiTheme, type UiTheme, useUiTheme } from "@/lib/ui-theme";
import { cn } from "@/lib/utils";
import type { SettingEntry } from "./settingsModel";

/** Body text is 0.8125rem; a size names the pixels a reader gets. */
const BODY_REM = 0.8125;
const px = (percent: number): string =>
  `${Math.round(BODY_REM * 16 * (percent / 100) * 10) / 10} px`;

const THEMES: { id: UiTheme; label: string }[] = [
  { id: "light", label: "Light" },
  { id: "dark", label: "Dark" },
];

const ColorTheme = ({ category }: { category?: string }): JSX.Element => {
  const theme = useUiTheme();
  return (
    <SettingItem
      id="color-theme"
      category={category}
      title="Color theme"
      description="Light or dark."
    >
      <fieldset
        aria-label="Color theme"
        className="inline-flex w-fit gap-1 rounded-md border border-border p-hairline"
      >
        {THEMES.map((option) => (
          <button
            key={option.id}
            type="button"
            aria-pressed={theme === option.id}
            onClick={() => setUiTheme(option.id)}
            className={cn(
              "h-6 rounded-sm px-3 text-body focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
              theme === option.id
                ? "bg-accent-muted text-foreground"
                : "text-muted-foreground hover:bg-interactive",
            )}
          >
            {option.label}
          </button>
        ))}
      </fieldset>
    </SettingItem>
  );
};

const TextSize = ({ category }: { category?: string }): JSX.Element => {
  const active = useTextScale();
  return (
    <SettingItem
      id="text-size"
      category={category}
      title="Text size"
      description="The base size of text and controls across the workbench."
    >
      <Select value={active} onValueChange={setTextScale}>
        <SelectTrigger aria-label="Text size" className="w-60">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {TEXT_SCALES.map((option) => (
            <SelectItem key={option.id} value={option.id}>
              {option.label} · {px(option.percent)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </SettingItem>
  );
};

export const APPEARANCE_ENTRIES: readonly SettingEntry[] = [
  {
    id: "color-theme",
    title: "Color theme",
    description: "Light or dark.",
    keywords: ["theme", "dark mode", "light mode"],
    render: (category) => <ColorTheme key="color-theme" category={category} />,
  },
  {
    id: "text-size",
    title: "Text size",
    description: "The base size of text and controls across the workbench.",
    keywords: ["font", "zoom", "scale"],
    render: (category) => <TextSize key="text-size" category={category} />,
  },
];
