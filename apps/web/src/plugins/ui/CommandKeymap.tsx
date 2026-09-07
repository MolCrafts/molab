import { useEffect } from "react";
import { getCommand, listCommands } from "@/plugins/contributions/workbench";

const isEditableTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable;
};

export const eventMatchesKeybinding = (event: KeyboardEvent, binding: string): boolean => {
  const parts = binding
    .toLowerCase()
    .split("+")
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) return false;

  const wantShift = parts.includes("shift");
  const wantAlt = parts.includes("alt") || parts.includes("option");
  const wantCtrl = parts.includes("ctrl") || parts.includes("control");
  const wantMeta = parts.includes("meta") || parts.includes("cmd") || parts.includes("command");
  const wantMod = parts.includes("mod");

  const key = parts.find(
    (part) =>
      part !== "shift" &&
      part !== "alt" &&
      part !== "option" &&
      part !== "ctrl" &&
      part !== "control" &&
      part !== "meta" &&
      part !== "cmd" &&
      part !== "command" &&
      part !== "mod",
  );
  if (!key) return false;

  const eventKey = event.key.length === 1 ? event.key.toLowerCase() : event.key.toLowerCase();
  if (eventKey !== key && event.code.toLowerCase() !== `key${key}`) return false;
  if (Boolean(event.shiftKey) !== wantShift) return false;
  if (Boolean(event.altKey) !== wantAlt) return false;

  if (wantMod) {
    if (!(event.metaKey || event.ctrlKey)) return false;
  } else {
    if (Boolean(event.ctrlKey) !== wantCtrl) return false;
    if (Boolean(event.metaKey) !== wantMeta) return false;
  }
  return true;
};

/** Host keymap for plugin `commands.register(..., { keybinding })`. */
export const CommandKeymap = (): null => {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (isEditableTarget(event.target) && !(event.metaKey || event.ctrlKey)) {
        return;
      }
      for (const command of listCommands()) {
        if (!command.keybinding) continue;
        if (!eventMatchesKeybinding(event, command.keybinding)) continue;
        event.preventDefault();
        void command.run();
        return;
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return null;
};

export const runCommand = (id: string): boolean => {
  const command = getCommand(id);
  if (!command) return false;
  void command.run();
  return true;
};
