import { describe, expect, it } from "@rstest/core";
import { prettyKeys } from "./GlobalCommandPalette";

describe("prettyKeys", () => {
  it("reads registry keybindings as the keys on the keyboard", () => {
    expect(prettyKeys("alt+b")).toBe("⌥B");
    expect(prettyKeys("alt+bracketleft")).toBe("⌥[");
    expect(prettyKeys("shift+f6")).toBe("⇧F6");
    expect(prettyKeys("mod+shift+p")).toBe("⌘⇧P");
  });
});
