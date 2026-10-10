/**
 * Shell actions plugins may invoke (Reload / Reconnect). AppShell binds the
 * implementations; core plugin commands read them at click time.
 */

export interface HostActions {
  reloadWindow: () => void;
  reloadActiveView: () => void;
  reconnectRemote: () => void;
  isRemote: () => boolean;
}

const noop = (): void => {};

let actions: HostActions = {
  reloadWindow: noop,
  reloadActiveView: noop,
  reconnectRemote: noop,
  isRemote: () => false,
};

export const setHostActions = (next: Partial<HostActions>): void => {
  actions = { ...actions, ...next };
};

export const getHostActions = (): HostActions => actions;

export const resetHostActionsForTests = (): void => {
  actions = {
    reloadWindow: noop,
    reloadActiveView: noop,
    reconnectRemote: noop,
    isRemote: () => false,
  };
};
