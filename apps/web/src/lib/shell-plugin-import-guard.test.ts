import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "@rstest/core";

import { shellPluginImportOffenders } from "./shell-plugin-import-guard";

const srcRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

describe("shell plugin import guard", () => {
  it("registry paths do not import @/plugins/*", () => {
    expect(shellPluginImportOffenders(srcRoot)).toEqual([]);
  });
});
