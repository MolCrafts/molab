import { describe, expect, it } from "@rstest/core";

import { executionRelativePath, taskProducts } from "./taskProducts";

const claimsFile = (name: string): boolean => /\.(pdb|xyz|data|dcd)$/i.test(name);

describe("taskProducts", () => {
  it("keeps the formula and the files a plugin claims", () => {
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
            data: "/work/executions/e03/out/relax/network.data",
            dcd: "/work/executions/e03/out/relax/network.dcd",
            build_log: "/work/executions/e03/out/build/pbix-br.build.log",
          },
        },
      ],
      "e03",
      claimsFile,
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
          { key: "data", label: "network.data", path: "out/relax/network.data" },
          { key: "dcd", label: "network.dcd", path: "out/relax/network.dcd" },
        ],
      },
    ]);
  });

  it("drops a path that is not inside this attempt", () => {
    expect(executionRelativePath("/elsewhere/mol.pdb", "e01")).toBeNull();
  });
});
