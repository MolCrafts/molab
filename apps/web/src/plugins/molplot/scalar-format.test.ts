import { describe, expect, it } from "@rstest/core";

import { formatScalar } from "./scalar-format";

describe("formatScalar", () => {
  it("auto-picks scientific notation for tiny and large magnitudes", () => {
    expect(formatScalar(0.00012, { notation: "auto", significantDigits: 4 })).toBe("1.200e-4");
    expect(formatScalar(12345, { notation: "auto", significantDigits: 4 })).toBe("1.235e+4");
    expect(formatScalar(303.5, { notation: "auto", significantDigits: 4 })).toBe("303.5");
  });

  it("scientific notation always uses exponential form", () => {
    expect(formatScalar(303.537, { notation: "scientific", significantDigits: 4 })).toBe(
      "3.035e+2",
    );
  });

  it("decimal notation honours significant digits", () => {
    expect(formatScalar(1.23456, { notation: "decimal", significantDigits: 3 })).toBe("1.23");
  });
});
