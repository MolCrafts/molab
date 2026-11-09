/** Promise-style prompt (L13): a quick input under the title bar. */
import type { ReactNode } from "react";
import { useCallback, useState } from "react";
import { QuickInput } from "@/components/dialog/QuickInput";

export interface PromptOptions {
  title: ReactNode;
  description?: ReactNode;
  placeholder?: string;
  defaultValue?: string;
  label?: string;
  confirmLabel?: string;
  cancelLabel?: string;
}

interface InternalState extends PromptOptions {
  resolve: (value: string | null) => void;
}

interface UsePromptReturn {
  prompt: (options: PromptOptions) => Promise<string | null>;
  dialog: ReactNode;
}

export const usePrompt = (): UsePromptReturn => {
  const [state, setState] = useState<InternalState | null>(null);
  const [value, setValue] = useState("");

  const prompt = useCallback(
    (options: PromptOptions): Promise<string | null> =>
      new Promise<string | null>((resolve) => {
        // The value is in place before the input mounts, so it is selected on focus.
        setValue(options.defaultValue ?? "");
        setState({ ...options, resolve });
      }),
    [],
  );

  const close = (result: string | null): void => {
    if (state) {
      state.resolve(result);
      setState(null);
    }
  };

  const submit = (): void => {
    const trimmed = value.trim();
    close(trimmed.length === 0 ? null : trimmed);
  };

  // L13: a prompt is a quick input — one value, ↵ answers, Esc cancels.
  const dialog = (
    <QuickInput
      open={state !== null}
      onOpenChange={(open) => {
        if (!open) close(null);
      }}
      title={typeof state?.title === "string" ? state.title : (state?.label ?? "Enter a value")}
      prompt={
        <>
          {state?.title}
          {state?.label ? <> · {state.label}</> : null}
          {state?.description !== undefined ? <> · {state.description}</> : null}
          <span className="text-muted-foreground">
            {" "}
            · ↵ to {(state?.confirmLabel ?? "confirm").toLowerCase()}, Esc to cancel
          </span>
        </>
      }
      value={value}
      onValueChange={setValue}
      onSubmit={submit}
      placeholder={state?.placeholder}
    />
  );

  return { prompt, dialog };
};
