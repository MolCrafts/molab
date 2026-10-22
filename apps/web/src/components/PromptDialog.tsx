import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
} from "@molcrafts/ui";
import { Check, X } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";
import { WorkbenchAction } from "@/components/workbench";

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

  useEffect(() => {
    if (state) setValue(state.defaultValue ?? "");
  }, [state]);

  const prompt = useCallback(
    (options: PromptOptions): Promise<string | null> =>
      new Promise<string | null>((resolve) => {
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

  const handleSubmit = (event: React.FormEvent): void => {
    event.preventDefault();
    const trimmed = value.trim();
    close(trimmed.length === 0 ? null : trimmed);
  };

  const dialog = (
    <Dialog
      open={state !== null}
      onOpenChange={(open) => {
        if (!open) close(null);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{state?.title}</DialogTitle>
          {state?.description !== undefined && (
            <DialogDescription asChild>
              <div>{state.description}</div>
            </DialogDescription>
          )}
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            {state?.label && <Label htmlFor="prompt-input">{state.label}</Label>}
            <Input
              id="prompt-input"
              autoFocus
              value={value}
              placeholder={state?.placeholder}
              onChange={(event) => setValue(event.target.value)}
            />
          </div>
          <DialogFooter>
            <WorkbenchAction
              icon={<X aria-hidden />}
              kind="secondary"
              size="default"
              type="button"
              onClick={() => close(null)}
            >
              {state?.cancelLabel ?? "Cancel"}
            </WorkbenchAction>
            <WorkbenchAction
              icon={<Check aria-hidden />}
              kind="primary"
              size="default"
              type="submit"
            >
              {state?.confirmLabel ?? "OK"}
            </WorkbenchAction>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );

  return { prompt, dialog };
};
