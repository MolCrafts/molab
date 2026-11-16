/** Bottom-right notifications above the status bar (L13-8). */

import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import type { JSX } from "react";
import { DialogButton } from "@/components/dialog/AppDialog";
import { WorkbenchIconAction } from "@/components/workbench";
import { dismissNotification, type Notification, useNotifications } from "./notificationStore";

const Lead = ({ kind }: { kind: Notification["kind"] }): JSX.Element =>
  kind === "error" ? (
    <CircleAlert
      className="mt-hairline size-icon flex-none text-status-failed-foreground"
      aria-hidden
    />
  ) : kind === "success" ? (
    <CircleCheck
      className="mt-hairline size-icon flex-none text-status-completed-foreground"
      aria-hidden
    />
  ) : (
    <Info className="mt-hairline size-icon flex-none text-muted-foreground" aria-hidden />
  );

export const NotificationHost = (): JSX.Element | null => {
  const notifications = useNotifications();
  if (notifications.length === 0) return null;
  return (
    <section
      aria-label="Notifications"
      className="pointer-events-none fixed right-3 bottom-8 z-50 flex w-shell-preview max-w-overlay-viewport flex-col gap-2"
    >
      {notifications.map((item) => (
        <div
          key={item.id}
          role={item.kind === "error" ? "alert" : "status"}
          className="mol-motion-enter-from-right pointer-events-auto rounded-panel border border-border bg-background py-2 pr-2 pl-3 shadow-overlay"
        >
          <div className="flex items-start gap-2">
            <Lead kind={item.kind} />
            <p className="min-w-0 flex-1 break-words text-body leading-relaxed">{item.message}</p>
            <WorkbenchIconAction
              size="shell"
              label="Dismiss notification"
              onClick={() => dismissNotification(item.id)}
            >
              <X aria-hidden />
            </WorkbenchIconAction>
          </div>
          {item.action ? (
            <div className="flex justify-end pt-2">
              <DialogButton
                kind="secondary"
                type="button"
                onClick={() => {
                  dismissNotification(item.id);
                  item.action?.onClick();
                }}
              >
                {item.action.label}
              </DialogButton>
            </div>
          ) : null}
        </div>
      ))}
    </section>
  );
};
