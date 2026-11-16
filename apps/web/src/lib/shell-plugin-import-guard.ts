/**
 * Ensures shell registry paths do not import bundled plugin modules.
 *
 * Plugins must not import ``@/app/registry`` (they `activate(api)`). The
 * reverse also must not hold for the contribution registry stack under
 * ``app/registry`` and ``lib/`` helpers.
 */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { collectImportSpecifiers } from "@/plugins/import-guard";

export type ShellPluginImportHit = {
  file: string;
  specifier: string;
};

/** Registry-path files that must stay plugin-free. */
export const SHELL_REGISTRY_GUARD_FILES: readonly string[] = [
  "app/registry.ts",
  "lib/contribution-runtime.ts",
  "lib/contribution-types.ts",
  "lib/file-type-discovery.ts",
  "lib/file-preview-plugins.ts",
];

const PLUGIN_IMPORT = /^@\/plugins\//;

export const shellPluginImportOffenders = (srcRoot: string): ShellPluginImportHit[] => {
  const hits: ShellPluginImportHit[] = [];
  for (const rel of SHELL_REGISTRY_GUARD_FILES) {
    const full = join(srcRoot, rel);
    if (!existsSync(full)) continue;
    const source = readFileSync(full, "utf8");
    for (const specifier of collectImportSpecifiers(source)) {
      if (PLUGIN_IMPORT.test(specifier)) {
        hits.push({ file: rel, specifier });
      }
    }
  }
  return hits;
};
