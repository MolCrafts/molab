/**
 * Promise-style confirm and alert (L13): one dialog shape for every "are you
 * sure" — Cancel · Primary text buttons, a destructive primary in danger, focus
 * starting on Cancel. Replaces the icon-only ✓ ✕ and the native `confirm`.
 */
import type { ReactNode } from "react";
import { useCallback, useState } from "react";
import { AppDialog } from "@/components/dialog/AppDialog";

export interface ConfirmOptions {
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
}

interface InternalState extends ConfirmOptions {
  resolve: (value: boolean) => void;
}

export interface UseConfirmReturn {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  dialog: ReactNode;
}

export const useConfirm = (): UseConfirmReturn => {
  const [state, setState] = useState<InternalState | null>(null);

  const confirm = useCallback(
    (options: ConfirmOptions): Promise<boolean> =>
      new Promise<boolean>((resolve) => {
        setState({ ...options, resolve });
      }),
    [],
  );

  const close = (value: boolean): void => {
    if (state) {
      state.resolve(value);
      setState(null);
    }
  };

  const dialog = (
    <AppDialog
      open={state !== null}
      onOpenChange={(open) => {
        if (!open) close(false);
      }}
      size="confirm"
      title={state?.title}
      message={state?.description}
      primaryLabel={state?.confirmLabel ?? "Confirm"}
      cancelLabel={state?.cancelLabel ?? "Cancel"}
      danger={Boolean(state?.destructive)}
      onPrimary={() => close(true)}
    />
  );

  return { confirm, dialog };
};

export interface AlertOptions {
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
}

interface InternalAlertState extends AlertOptions {
  resolve: () => void;
}

export interface UseAlertReturn {
  alert: (options: AlertOptions) => Promise<void>;
  dialog: ReactNode;
}

export const useAlert = (): UseAlertReturn => {
  const [state, setState] = useState<InternalAlertState | null>(null);

  const alert = useCallback(
    (options: AlertOptions): Promise<void> =>
      new Promise<void>((resolve) => {
        setState({ ...options, resolve });
      }),
    [],
  );

  const close = (): void => {
    if (state) {
      state.resolve();
      setState(null);
    }
  };

  const dialog = (
    <AppDialog
      open={state !== null}
      onOpenChange={(open) => {
        if (!open) close();
      }}
      size="confirm"
      alert
      title={state?.title}
      message={state?.description}
      primaryLabel={state?.confirmLabel ?? "OK"}
      onPrimary={() => close()}
    />
  );

  return { alert, dialog };
};
