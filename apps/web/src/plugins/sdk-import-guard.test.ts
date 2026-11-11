import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "@rstest/core";
import { collectImportSpecifiers } from "@/plugins/import-guard";

const here = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(here, "..");
const pluginSrc = resolve(here, "../../../plugin/src");
const fixtureSrc = resolve(here, "../../../../tests/test_plugins/_fixtures/example_plugin/ui_dist");

const walkTsFiles = (dir: string, acc: string[]): void => {
  if (!existsSync(dir)) return;
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      walkTsFiles(full, acc);
      continue;
    }
    if (entry.endsWith(".ts") || entry.endsWith(".tsx") || entry.endsWith(".js")) {
      acc.push(full);
    }
  }
};

const registryImport = /^@\/app\/registry/;

describe("plugin SDK import guard", () => {
  it("SDK package does not import @/app/registry", () => {
    const files: string[] = [];
    walkTsFiles(pluginSrc, files);
    const hits: string[] = [];
    for (const file of files) {
      const source = readFileSync(file, "utf8");
      for (const specifier of collectImportSpecifiers(source)) {
        if (registryImport.test(specifier)) {
          hits.push(`${relative(pluginSrc, file)}:${specifier}`);
        }
      }
    }
    expect(hits).toEqual([]);
  });

  it("internal plugin implementations do not import @/app/registry", () => {
    const files: string[] = [];
    walkTsFiles(join(webSrc, "plugins"), files);
    const hits: string[] = [];
    for (const file of files) {
      const rel = relative(webSrc, file).replace(/\\/g, "/");
      if (rel.endsWith(".test.ts") || rel.endsWith(".test.tsx")) continue;
      const source = readFileSync(file, "utf8");
      for (const specifier of collectImportSpecifiers(source)) {
        if (registryImport.test(specifier)) {
          hits.push(`${rel}:${specifier}`);
        }
      }
    }
    expect(hits).toEqual([]);
  });

  it("example remote fixture does not import @/app/registry", () => {
    const entry = join(fixtureSrc, "index.js");
    expect(existsSync(entry)).toBe(true);
    const source = readFileSync(entry, "utf8");
    expect(collectImportSpecifiers(source).filter((s) => registryImport.test(s))).toEqual([]);
  });
});
