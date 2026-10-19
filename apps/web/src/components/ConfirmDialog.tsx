import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@molcrafts/ui";
import { Check, X } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useState } from "react";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

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

interface UseConfirmReturn {
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
    <AlertDialog
      open={state !== null}
      onOpenChange={(open) => {
        if (!open) close(false);
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{state?.title}</AlertDialogTitle>
          {state?.description !== undefined && (
            <AlertDialogDescription asChild>
              <div>{state.description}</div>
            </AlertDialogDescription>
          )}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel
            className="size-control-compact bg-transparent p-0 text-foreground hover:bg-interactive"
            asChild
          >
            <WorkbenchIconAction
              label={state?.cancelLabel ?? "Cancel"}
              onClick={() => close(false)}
            >
              <X aria-hidden />
            </WorkbenchIconAction>
          </AlertDialogCancel>
          <AlertDialogAction
            className={cn(
              "size-control-compact bg-transparent p-0 hover:bg-interactive",
              state?.destructive
                ? "text-destructive hover:text-destructive"
                : "text-foreground hover:text-foreground",
            )}
            asChild
          >
            <WorkbenchIconAction
              label={state?.confirmLabel ?? "Confirm"}
              kind={state?.destructive ? "danger" : "ghost"}
              onClick={() => close(true)}
            >
              <Check aria-hidden />
            </WorkbenchIconAction>
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
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

interface UseAlertReturn {
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
    <AlertDialog
      open={state !== null}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{state?.title}</AlertDialogTitle>
          {state?.description !== undefined && (
            <AlertDialogDescription asChild>
              <div>{state.description}</div>
            </AlertDialogDescription>
          )}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogAction
            className="size-control-compact bg-transparent p-0 text-foreground hover:bg-interactive hover:text-foreground"
            asChild
          >
            <WorkbenchIconAction label={state?.confirmLabel ?? "OK"} onClick={() => close()}>
              <Check aria-hidden />
            </WorkbenchIconAction>
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return { alert, dialog };
};
