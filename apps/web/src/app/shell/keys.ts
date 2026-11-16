/** Shortcut labels for the platform the browser runs on (⌘⌥⇧ on macOS, Ctrl / Alt elsewhere). */

const isMac = (): boolean => {
  try {
    return /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent);
  } catch {
    return false;
  }
};

export const shortcut = (keys: {
  mod?: boolean;
  alt?: boolean;
  shift?: boolean;
  key: string;
}): string => {
  const mac = isMac();
  const parts = [
    keys.shift ? (mac ? "⇧" : "Shift+") : "",
    keys.alt ? (mac ? "⌥" : "Alt+") : "",
    keys.mod ? (mac ? "⌘" : "Ctrl+") : "",
  ];
  return `${parts.join("")}${keys.key}`;
};

export const SHORTCUTS = {
  goTo: () => shortcut({ mod: true, key: "K" }),
  commands: () => shortcut({ mod: true, shift: true, key: "P" }),
  regions: () => "F6",
  sideBar: () => shortcut({ alt: true, key: "B" }),
  panel: () => shortcut({ alt: true, key: "J" }),
  closeEditor: () => shortcut({ alt: true, key: "W" }),
} as const;
