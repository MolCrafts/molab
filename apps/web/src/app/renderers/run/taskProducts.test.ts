import { describe, expect, it } from "@rstest/core";

import { executionRelativePath, taskProducts } from "./taskProducts";

describe("taskProducts", () => {
  it("keeps the formula and the structure paths of one task", () => {
    const rows = taskProducts(
      [
        {
          id: "build_fragment",
          status: "completed",
          outputs: {
            real_formula: "C9H10Br",
            ports: 1,
            pdb: "/work/executions/e03/out/build/pbix-br.pdb",
            xyz: "/work/executions/e03/out/build/pbix-br.xyz",
            build_log: "/work/executions/e03/out/build/pbix-br.build.log",
          },
        },
      ],
      "e03",
    );
    expect(rows).toEqual([
      {
        taskId: "build_fragment",
        status: "completed",
        scalars: [
          { key: "real_formula", value: "C9H10Br" },
          { key: "ports", value: "1" },
        ],
        structures: [
          { key: "pdb", label: "pbix-br.pdb", path: "out/build/pbix-br.pdb" },
          { key: "xyz", label: "pbix-br.xyz", path: "out/build/pbix-br.xyz" },
        ],
      },
    ]);
  });

  it("drops a path that is not inside this attempt", () => {
    expect(executionRelativePath("/elsewhere/mol.pdb", "e01")).toBeNull();
  });
});
