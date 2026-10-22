import { Button } from "@molcrafts/ui";
import { Moon, Sun } from "lucide-react";
import { SettingsRow } from "@/components/settings";
import { WorkbenchIconAction } from "@/components/workbench";
import { setTextScale, TEXT_SCALES, useTextScale } from "@/lib/ui-scale";
import { setUiTheme, useUiTheme } from "@/lib/ui-theme";

/** Body text is 0.8125rem; show the size a reader will actually get. */
const BODY_REM = 0.8125;

export function AppearancePanel(): JSX.Element {
  const active = useTextScale();
  const theme = useUiTheme();

  return (
    <div className="space-y-3">
      <SettingsRow label="Color theme">
        <fieldset aria-label="Color theme" className="flex gap-1">
          <WorkbenchIconAction
            label="Light theme"
            aria-pressed={theme === "light"}
            className={theme === "light" ? "bg-interactive" : undefined}
            onClick={() => setUiTheme("light")}
          >
            <Sun aria-hidden />
          </WorkbenchIconAction>
          <WorkbenchIconAction
            label="Dark theme"
            aria-pressed={theme === "dark"}
            className={theme === "dark" ? "bg-interactive" : undefined}
            onClick={() => setUiTheme("dark")}
          >
            <Moon aria-hidden />
          </WorkbenchIconAction>
        </fieldset>
      </SettingsRow>
      <SettingsRow label="Text size">
        <div role="radiogroup" aria-label="Text size" className="flex flex-wrap gap-1">
          {TEXT_SCALES.map((option) => {
            const selected = option.id === active;
            return (
              <Button
                key={option.id}
                type="button"
                role="radio"
                aria-checked={selected}
                variant="ghost"
                className={selected ? "bg-interactive text-foreground" : "text-muted-foreground"}
                size="sm"
                onClick={() => setTextScale(option.id)}
              >
                {option.label}
                <span className="font-mono text-micro opacity-70">
                  {Math.round(BODY_REM * 16 * (option.percent / 100) * 10) / 10}px
                </span>
              </Button>
            );
          })}
        </div>
      </SettingsRow>
    </div>
  );
}
