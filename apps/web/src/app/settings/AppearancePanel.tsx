import { SettingsRow } from "@/components/settings";
import { Button } from "@/components/ui/button";
import { setTextScale, TEXT_SCALES, useTextScale } from "@/lib/ui-scale";

/** Body text is 0.8125rem; show the size a reader will actually get. */
const BODY_REM = 0.8125;

export function AppearancePanel(): JSX.Element {
  const active = useTextScale();

  return (
    <div className="space-y-3">
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
                variant={selected ? "default" : "outline"}
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
      <p className="px-1 text-micro text-muted-foreground">
        Scales all text, controls, and spacing. Saved in this browser only.
      </p>
    </div>
  );
}
