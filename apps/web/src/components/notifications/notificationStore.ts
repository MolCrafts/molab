/**
 * Notifications (L13, Figma L13-8): the result of something you just did.
 * Two channels, one rule: an error, or a result that offers a follow-up
 * action, floats bottom-right; a plain confirmation ("Copied") or progress
 * stays in the status bar. At most three; errors stay until dismissed,
 * results clear after six seconds.
 */

import { useSyncExternalStore } from "react";

export type NotificationKind = "default" | "success" | "error";

export interface NotificationAction {
  label: string;
  onClick: () => void;
}

export interface Notification {
  id: string;
  kind: NotificationKind;
  message: string;
  action?: NotificationAction;
}

export const MAX_NOTIFICATIONS = 3;
export const RESULT_LIFETIME_MS = 6_000;

export const routeOf = (kind: NotificationKind, hasAction: boolean): "notification" | "status" =>
  kind === "error" || hasAction ? "notification" : "status";

/** Newest at the bottom; the same message replaces itself; the oldest goes past three. */
export const addNotification = (
  list: readonly Notification[],
  next: Notification,
): Notification[] => {
  const without = list.filter((item) => item.message !== next.message);
  return [...without, next].slice(-MAX_NOTIFICATIONS);
};

let notifications: Notification[] = [];
const listeners = new Set<() => void>();
let sequence = 0;

const emit = (): void => {
  for (const listener of listeners) listener();
};

export const dismissNotification = (id: string): void => {
  notifications = notifications.filter((item) => item.id !== id);
  emit();
};

export const pushNotification = (
  notification: Omit<Notification, "id">,
  lifetimeMs: number = RESULT_LIFETIME_MS,
): string => {
  sequence += 1;
  const id = `n${sequence}`;
  notifications = addNotification(notifications, { ...notification, id });
  emit();
  if (notification.kind !== "error") {
    setTimeout(() => dismissNotification(id), lifetimeMs);
  }
  return id;
};

const subscribe = (listener: () => void): (() => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export const useNotifications = (): readonly Notification[] =>
  useSyncExternalStore(
    subscribe,
    () => notifications,
    () => notifications,
  );
