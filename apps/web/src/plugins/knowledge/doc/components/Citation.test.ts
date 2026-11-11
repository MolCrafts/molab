import { describe, expect, it } from "@rstest/core";
import { bareDoi } from "./Citation";

describe("bareDoi", () => {
  it("strips a doi: prefix and a doi.org URL", () => {
    expect(bareDoi("10.1080/0026.987")).toBe("10.1080/0026.987");
    expect(bareDoi("doi:10.1080/0026.987")).toBe("10.1080/0026.987");
    expect(bareDoi("https://doi.org/10.1080/0026.987")).toBe("10.1080/0026.987");
    expect(bareDoi("https://dx.doi.org/10.1/x")).toBe("10.1/x");
  });
});
