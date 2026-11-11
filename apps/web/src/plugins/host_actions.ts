/**
 * Shell actions plugins may invoke (Reload / Reconnect). AppShell binds the
 * implementations; core plugin commands read them at click time.
 */

export interface HostActions {
  reloadWindow: () => void;
  reloadActiveView: () => void;
  reconnectRemote: () => void;
  isRemote: () => boolean;
  /** Shell layout (L00): side bar, bottom panel, editor tabs, F6 regions. */
  toggleSideBar: () => void;
  togglePanel: () => void;
  hasPanel: () => boolean;
  closeEditor: () => void;
  cycleEditor: (delta: number) => void;
  focusRegion: (delta: number) => void;
}

const noop = (): void => {};

const defaultActions = (): HostActions => ({
  reloadWindow: noop,
  reloadActiveView: noop,
  reconnectRemote: noop,
  isRemote: () => false,
  toggleSideBar: noop,
  togglePanel: noop,
  hasPanel: () => false,
  closeEditor: noop,
  cycleEditor: noop,
  focusRegion: noop,
});

let actions: HostActions = defaultActions();

export const setHostActions = (next: Partial<HostActions>): void => {
  actions = { ...actions, ...next };
};

export const getHostActions = (): HostActions => actions;

export const resetHostActionsForTests = (): void => {
  actions = defaultActions();
};
