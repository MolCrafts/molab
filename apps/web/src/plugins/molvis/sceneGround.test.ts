import { describe, expect, it } from "@rstest/core";

import { cssColourToHex, hexFromRgb } from "./sceneGround";

describe("hexFromRgb", () => {
  it("writes three channels as #rrggbb", () => {
    expect(hexFromRgb(255, 255, 255)).toBe("#ffffff");
    expect(hexFromRgb(0, 16, 1)).toBe("#001001");
  });

  it("clamps and rounds out-of-range channels", () => {
    expect(hexFromRgb(-4, 300, 127.6)).toBe("#00ff80");
  });
});

describe("cssColourToHex", () => {
  it("is null without a DOM (the stage keeps its own ground)", () => {
    expect(cssColourToHex("white")).toBeNull();
  });
});
