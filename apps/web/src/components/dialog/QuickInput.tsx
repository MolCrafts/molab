/**
 * Quick input (L13, Figma L13-4): one value, top-anchored under the title bar —
 * rename, add workspace, verification code. A prompt line says what is asked
 * and how to answer; an error or hint sits under the field. ↵ submits, Esc
 * cancels. One component replaces the prompt dialog and two copied shells.
 */

import { Dialog, DialogContent, DialogDescription, DialogTitle, Input } from "@molcrafts/ui";
import { CircleAlert, Loader2 } from "lucide-react";
import {
  type InputHTMLAttributes,
  type JSX,
  type ReactNode,
  useEffect,
  useId,
  useRef,
} from "react";
import { cn } from "@/lib/utils";

export interface QuickInputProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** What is asked, for assistive tech and the prompt line. */
  title: string;
  /** The prompt line under the title: how to answer. */
  prompt?: ReactNode;
  value: string;
  onValueChange: (value: string) => void;
  onSubmit: () => void;
  placeholder?: string;
  /** Under the field: an error (danger) or a quiet hint. */
  error?: ReactNode;
  hint?: ReactNode;
  busy?: boolean;
  mono?: boolean;
  /** A prompt that must be answered (verification code): no outside click. */
  blocking?: boolean;
  onEscape?: () => void;
  inputProps?: Pick<
    InputHTMLAttributes<HTMLInputElement>,
    "autoComplete" | "inputMode" | "spellCheck"
  >;
}

export const QuickInput = ({
  open,
  onOpenChange,
  title,
  prompt,
  value,
  onValueChange,
  onSubmit,
  placeholder,
  error,
  hint,
  busy = false,
  mono = false,
  blocking = false,
  onEscape,
  inputProps,
}: QuickInputProps): JSX.Element => {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  // Focus and select once the content is mounted (Radix autofocus is off so a
  // pre-filled value is selected, as in VS Code's rename).
  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
    return () => cancelAnimationFrame(frame);
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className={cn(
          "top-shell-titlebar max-w-overlay-viewport -translate-y-0 gap-0 overflow-hidden p-2 sm:max-w-quick-input",
          "rounded-panel",
        )}
        onOpenAutoFocus={(event) => event.preventDefault()}
        onInteractOutside={blocking ? (event) => event.preventDefault() : undefined}
        onEscapeKeyDown={(event) => {
          if (!onEscape) return;
          event.preventDefault();
          onEscape();
        }}
      >
        <DialogTitle className="sr-only">{title}</DialogTitle>
        <DialogDescription className="px-2 pt-hairline pb-2 text-label text-muted-foreground">
          {prompt ?? title}
        </DialogDescription>
        <form
          className="relative flex items-center"
          onSubmit={(event) => {
            event.preventDefault();
            if (!busy) onSubmit();
          }}
        >
          <Input
            ref={inputRef}
            id={inputId}
            value={value}
            disabled={busy}
            placeholder={placeholder}
            autoComplete="off"
            spellCheck={false}
            {...inputProps}
            aria-invalid={Boolean(error)}
            aria-describedby={error || hint ? `${inputId}-note` : undefined}
            onChange={(event) => onValueChange(event.target.value)}
            className={cn(
              "h-control-compact rounded-hairline border-accent shadow-none ring-1 ring-accent focus-visible:ring-1 focus-visible:ring-accent",
              error && "border-destructive ring-destructive focus-visible:ring-destructive",
              mono && "font-mono",
            )}
          />
          {busy ? (
            <Loader2
              className="mol-motion-progress-spin pointer-events-none absolute right-2 size-icon-sm text-muted-foreground"
              aria-hidden
            />
          ) : null}
        </form>
        {error ? (
          <p
            id={`${inputId}-note`}
            role="alert"
            className="flex items-center gap-1 px-2 pt-2 text-label text-status-failed-foreground"
          >
            <CircleAlert className="size-icon-sm flex-none" aria-hidden />
            {error}
          </p>
        ) : hint ? (
          <p id={`${inputId}-note`} className="px-2 pt-2 text-label text-muted-foreground">
            {hint}
          </p>
        ) : null}
      </DialogContent>
    </Dialog>
  );
};
