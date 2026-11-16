/**
 * The one dialog (L13, Figma L13-1 … L13-3): title · optional message · body ·
 * an error above the footer · footer with the ⌘↵ hint at the left and
 * Cancel · Primary at the right (VS Code order). Three widths — confirm, form,
 * wide — from the constitution's dialog sizes. On phones it is a bottom sheet
 * with full-width buttons, primary first.
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
  Kbd,
} from "@molcrafts/ui";
import { CircleAlert, X } from "lucide-react";
import type { FormEvent, JSX, ReactNode } from "react";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";
import { isSubmitShortcut } from "./dialogKeys";

export type DialogSize = "confirm" | "form" | "wide";

const WIDTH: Record<DialogSize, string> = {
  confirm: "sm:max-w-dialog-sm",
  form: "sm:max-w-dialog-md",
  wide: "sm:max-w-dialog-lg",
};

export interface AppDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  /** The consequence, one or two lines (a confirm's whole body). */
  message?: ReactNode;
  size?: DialogSize;
  /** The verb + noun of the title: "Create run", "Delete experiment". */
  primaryLabel: string;
  onPrimary: () => void | Promise<void>;
  primaryDisabled?: boolean;
  /** While true both buttons disable and the primary reads `busyLabel`. */
  busy?: boolean;
  busyLabel?: string;
  danger?: boolean;
  cancelLabel?: string;
  /** An alert has no Cancel: one acknowledgement button. */
  alert?: boolean;
  /** A request error; field errors sit under their field. */
  error?: ReactNode;
  trigger?: ReactNode;
  /**
   * Whether ↵ in a one-line field submits (default). Editors that are still
   * being filled in (sweep axes, a document form) turn it off: ⌘↵ only.
   */
  submitOnEnter?: boolean;
  children?: ReactNode;
}

export const DialogButton = ({
  kind,
  size = "default",
  children,
  className,
  ...rest
}: {
  kind: "primary" | "secondary" | "danger";
  /**
   * `chrome`: a button in the editor chrome — the tab row's page actions, a
   * view's toolbar — 22px with 12px text, as VS Code draws its title-area buttons.
   */
  size?: "default" | "chrome";
  children: ReactNode;
} & React.ButtonHTMLAttributes<HTMLButtonElement>): JSX.Element => (
  <button
    {...rest}
    className={cn(
      "inline-flex items-center justify-center whitespace-nowrap rounded-hairline outline-none",
      size === "chrome"
        ? "h-shell-action px-2 text-label"
        : "h-shell-button min-w-16 px-3 text-body max-sm:h-touch-target max-sm:w-full",
      "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:opacity-60",
      kind === "primary" && "bg-accent text-accent-foreground hover:bg-accent-hover",
      kind === "danger" &&
        "bg-destructive text-destructive-foreground hover:bg-status-failed-hover",
      kind === "secondary" && "bg-interactive text-foreground hover:bg-interactive-pressed",
      className,
    )}
  >
    {children}
  </button>
);

export const AppDialog = ({
  open,
  onOpenChange,
  title,
  message,
  size = "form",
  primaryLabel,
  onPrimary,
  primaryDisabled = false,
  busy = false,
  busyLabel,
  danger = false,
  cancelLabel = "Cancel",
  alert = false,
  error,
  trigger,
  submitOnEnter = true,
  children,
}: AppDialogProps): JSX.Element => {
  const disabled = primaryDisabled || busy;
  // A dialog opened from inside another (Add target inside New run) renders in
  // a portal but bubbles through React: its submit must not reach the outer form.
  const submit = (event?: FormEvent): void => {
    event?.preventDefault();
    event?.stopPropagation();
    if (!disabled) void onPrimary();
  };
  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      {trigger ? <DialogTrigger asChild>{trigger}</DialogTrigger> : null}
      <DialogContent
        showCloseButton={false}
        role={alert || danger ? "alertdialog" : "dialog"}
        className={cn(
          "gap-0 overflow-hidden p-0",
          WIDTH[size],
          // Phones: a bottom sheet (L13-9a).
          "max-sm:top-auto max-sm:bottom-0 max-sm:left-0 max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:rounded-b-none",
        )}
        // A notification floats above the dialog; using it is not "outside".
        onInteractOutside={(event) => {
          const target = event.target as HTMLElement | null;
          if (target?.closest('[aria-label="Notifications"]')) event.preventDefault();
        }}
        onKeyDown={(event) => {
          const target = event.target as HTMLElement;
          // An open select list owns ↵ and ⌘↵ until it closes.
          if (target.closest('[role="listbox"]')) return;
          if (
            !submitOnEnter &&
            event.key === "Enter" &&
            !event.metaKey &&
            !event.ctrlKey &&
            target instanceof HTMLInputElement
          ) {
            event.preventDefault();
            return;
          }
          if (isSubmitShortcut(event.nativeEvent)) {
            event.preventDefault();
            event.stopPropagation();
            submit();
          }
        }}
        // A destructive confirm starts on Cancel; a form on its first field;
        // anything else on its primary — never on the header ✕.
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          const root = event.currentTarget as HTMLElement;
          const target = danger
            ? root.querySelector<HTMLElement>('[data-dialog-cancel="true"]')
            : (root.querySelector<HTMLElement>(
                "input:not([type=hidden]):not([disabled]), textarea:not([disabled]), [role=combobox]:not([disabled])",
              ) ?? root.querySelector<HTMLElement>('button[type="submit"]'));
          target?.focus();
        }}
      >
        <form onSubmit={submit} className="flex min-h-0 flex-col">
          <div className="flex h-10 items-center justify-between gap-2 pr-2 pl-4">
            <DialogTitle className="min-w-0 truncate text-body font-semibold">{title}</DialogTitle>
            <WorkbenchIconAction
              size="shell"
              label="Close"
              type="button"
              disabled={busy}
              onClick={() => onOpenChange(false)}
            >
              <X aria-hidden />
            </WorkbenchIconAction>
          </div>
          <div className="max-h-dialog-scroll space-y-4 overflow-y-auto px-4 pt-1 pb-4">
            {message ? (
              <DialogDescription className="text-body leading-relaxed text-foreground">
                {message}
              </DialogDescription>
            ) : (
              <DialogDescription className="sr-only">{primaryLabel}</DialogDescription>
            )}
            {children}
          </div>
          {error ? (
            <p
              role="alert"
              className="flex items-start gap-2 border-t border-border px-4 py-2 text-label text-status-failed-foreground"
            >
              <CircleAlert className="mt-hairline size-icon-sm flex-none" aria-hidden />
              <span className="min-w-0 break-words">{error}</span>
            </p>
          ) : null}
          <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-2 max-sm:flex-col-reverse max-sm:items-stretch max-sm:pb-6">
            <span className="flex items-center gap-1 text-label text-muted-foreground max-sm:hidden">
              <Kbd>⌘↵</Kbd>
              {alert ? "to close" : "to confirm"}
            </span>
            <div className="flex items-center gap-2 max-sm:flex-col-reverse max-sm:items-stretch">
              {alert ? null : (
                <DialogButton
                  kind="secondary"
                  type="button"
                  data-dialog-cancel="true"
                  disabled={busy}
                  onClick={() => onOpenChange(false)}
                >
                  {cancelLabel}
                </DialogButton>
              )}
              <DialogButton kind={danger ? "danger" : "primary"} type="submit" disabled={disabled}>
                {busy ? (busyLabel ?? `${primaryLabel}…`) : primaryLabel}
              </DialogButton>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};
