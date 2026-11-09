/**
 * One feedback API, two channels (L13-8). An error, or a result that offers
 * a follow-up `action`, becomes a notification bottom-right; a plain
 * confirmation ("Copied") stays a one-line report in the status bar.
 *
 * Call `toast("Copied")`, `toast.success("Attempt e02 created", { action })`
 * or `toast.error("…")` from anywhere.
 */

import { createContext, type ReactNode, useContext, useMemo } from "react";

import { pushNotification, routeOf } from "@/components/notifications/notificationStore";
import { reportStatus, type StatusReportType } from "@/lib/status-report";

export type ToastKind = "default" | "success" | "error";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastOptions {
  kind?: ToastKind;
  durationMs?: number;
  /** A follow-up ("Open attempt") — makes the message a notification. */
  action?: ToastAction;
}

type ToastFn = ((message: string, options?: ToastOptions) => void) & {
  success: (message: string, options?: Omit<ToastOptions, "kind">) => void;
  error: (message: string, options?: Omit<ToastOptions, "kind">) => void;
};

function kindToType(kind: ToastKind | undefined): StatusReportType {
  if (kind === "error") return "error";
  if (kind === "success") return "success";
  return "info";
}

function push(message: string, options?: ToastOptions): void {
  const text = message.trim();
  if (!text) return;
  const kind = options?.kind ?? "default";
  if (routeOf(kind, Boolean(options?.action)) === "notification") {
    pushNotification({ kind, message: text, action: options?.action }, options?.durationMs);
    return;
  }
  reportStatus(text, kindToType(kind));
}

/** Imperative API (usable outside React trees). */
export const toast: ToastFn = Object.assign(
  (message: string, options?: ToastOptions) => {
    push(message, options);
  },
  {
    success: (message: string, options?: Omit<ToastOptions, "kind">) => {
      push(message, { ...options, kind: "success" });
    },
    error: (message: string, options?: Omit<ToastOptions, "kind">) => {
      push(message, { ...options, kind: "error" });
    },
  },
);

const ToastContext = createContext<ToastFn | null>(null);

export function useToast(): ToastFn {
  return useContext(ToastContext) ?? toast;
}

/**
 * Passthrough provider — no floating toast host.
 * Kept so root mounts and tests that wrap with ToastProvider still compile.
 */
export function ToastProvider({ children }: { children: ReactNode }): JSX.Element {
  const api = useMemo<ToastFn>(() => toast, []);
  return <ToastContext.Provider value={api}>{children}</ToastContext.Provider>;
}
