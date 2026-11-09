import { describe, expect, it } from "@rstest/core";
import { eventMatchesKeybinding } from "./CommandKeymap";

const key = (init: Partial<KeyboardEvent> & { key: string; code: string }): KeyboardEvent =>
  ({
    shiftKey: false,
    altKey: false,
    ctrlKey: false,
    metaKey: false,
    ...init,
  }) as KeyboardEvent;

describe("eventMatchesKeybinding", () => {
  it("matches ⌥B on macOS, where the key is a composed glyph", () => {
    expect(eventMatchesKeybinding(key({ key: "∫", code: "KeyB", altKey: true }), "alt+b")).toBe(
      true,
    );
  });

  it("matches ⌥[ / ⌥] by physical key, whatever the layout composes", () => {
    const left = key({ key: "“", code: "BracketLeft", altKey: true });
    const right = key({ key: "‘", code: "BracketRight", altKey: true });
    expect(eventMatchesKeybinding(left, "alt+bracketleft")).toBe(true);
    expect(eventMatchesKeybinding(right, "alt+bracketright")).toBe(true);
    expect(eventMatchesKeybinding(right, "alt+bracketleft")).toBe(false);
  });

  it("matches function keys with and without shift", () => {
    expect(eventMatchesKeybinding(key({ key: "F6", code: "F6" }), "f6")).toBe(true);
    expect(eventMatchesKeybinding(key({ key: "F6", code: "F6", shiftKey: true }), "f6")).toBe(
      false,
    );
    expect(eventMatchesKeybinding(key({ key: "F6", code: "F6", shiftKey: true }), "shift+f6")).toBe(
      true,
    );
  });

  it("requires the exact modifiers", () => {
    expect(eventMatchesKeybinding(key({ key: "b", code: "KeyB" }), "alt+b")).toBe(false);
    expect(
      eventMatchesKeybinding(key({ key: "b", code: "KeyB", altKey: true, metaKey: true }), "alt+b"),
    ).toBe(false);
  });
});
