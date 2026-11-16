import { describe, expect, it } from "@rstest/core";
import { isSubmitShortcut } from "./dialogKeys";

const key = (init: Partial<KeyboardEvent>): KeyboardEvent =>
  ({
    key: "Enter",
    metaKey: false,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    isComposing: false,
    ...init,
  }) as KeyboardEvent;

describe("isSubmitShortcut", () => {
  it("is ⌘↵ on macOS and Ctrl-↵ elsewhere", () => {
    expect(isSubmitShortcut(key({ metaKey: true }))).toBe(true);
    expect(isSubmitShortcut(key({ ctrlKey: true }))).toBe(true);
  });

  it("is not a plain ↵, another key, or ↵ while an IME composes", () => {
    expect(isSubmitShortcut(key({}))).toBe(false);
    expect(isSubmitShortcut(key({ key: "k", metaKey: true }))).toBe(false);
    expect(isSubmitShortcut(key({ metaKey: true, isComposing: true }))).toBe(false);
  });
});
