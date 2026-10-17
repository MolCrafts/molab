import { describe, expect, it } from "@rstest/core";
import { isMolabRef, type MolabRefTarget, resolveMolabRef } from "@/lib/molab-ref";

const index = new Map<string, MolabRefTarget>([
  ["molab:project/P1", { kind: "project", label: "PEO", path: "/projects/P1" }],
  ["molab:experiment/E1", { kind: "experiment", label: "Tg", path: "/projects/P1/experiments/E1" }],
  [
    "molab:experiment/E1/run/R1",
    { kind: "run", label: "n=8", path: "/projects/P1/experiments/E1/runs/R1" },
  ],
  [
    "molab:experiment/E2/run/R1",
    { kind: "run", label: "n=8", path: "/projects/P1/experiments/E2/runs/R1" },
  ],
]);

describe("isMolabRef", () => {
  it("accepts only the lower-case molab scheme", () => {
    expect(isMolabRef("molab:project/P1")).toBe(true);
    expect(isMolabRef("MOLAB:x")).toBe(false);
    expect(isMolabRef("https://x")).toBe(false);
    expect(isMolabRef(undefined)).toBe(false);
  });
});

describe("resolveMolabRef", () => {
  it("resolves an exact run ref", () => {
    const hit = resolveMolabRef("molab:experiment/E2/run/R1", index);
    expect(hit?.path).toBe("/projects/P1/experiments/E2/runs/R1");
    expect(hit?.rest).toBe("");
  });

  it("keeps an execution suffix under the owning run", () => {
    const hit = resolveMolabRef("molab:experiment/E1/run/R1/execution/e02", index);
    expect(hit?.kind).toBe("run");
    expect(hit?.ref).toBe("molab:experiment/E1/run/R1");
    expect(hit?.rest).toBe("execution/e02");
  });

  it("keeps an artifact suffix under the owning run", () => {
    const hit = resolveMolabRef("molab:experiment/E1/run/R1/artifact/A7", index);
    expect(hit?.rest).toBe("artifact/A7");
  });

  it("resolves an exact experiment ref", () => {
    const hit = resolveMolabRef("molab:experiment/E1", index);
    expect(hit?.kind).toBe("experiment");
    expect(hit?.rest).toBe("");
  });

  it("resolves an asset ref from the index", () => {
    const withAsset = new Map(index);
    withAsset.set("molab:asset/A1", { kind: "asset", label: "traj", path: "/assets/A1" });
    const hit = resolveMolabRef("molab:asset/A1", withAsset);
    expect(hit?.kind).toBe("asset");
    expect(hit?.path).toBe("/assets/A1");
  });

  it("rejects a suffix that is not under a known run", () => {
    expect(resolveMolabRef("molab:experiment/E1/run/R9", index)).toBeNull();
    expect(resolveMolabRef("molab:experiment/E1/extra", index)).toBeNull();
    expect(resolveMolabRef("molab:asset/X", index)).toBeNull();
    expect(resolveMolabRef("https://x", index)).toBeNull();
  });
});
