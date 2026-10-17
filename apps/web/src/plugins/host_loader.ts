/**
 * Rewrite remote plugin ESM so bare host specifiers resolve to the host's
 * singleton modules (one React, one SDK). Pattern copied from molvis page
 * loader — blob rewrite, not a document import map.
 */

import { getPluginHostModules, type PluginHostModules } from "./host_shared";

let importMapReady = false;
let pluginHostModules: PluginHostModules | undefined;
const moduleBlobUrls = new Map<string, string>();
const rewrittenModuleBlobs = new Map<string, string>();
const rewriteInFlight = new Map<string, Promise<string>>();
const graphChunks = new Map<string, Set<string>>();

function buildModuleBlob(spec: string, exports: Record<string, unknown>): string {
  const existing = moduleBlobUrls.get(spec);
  if (existing) return existing;

  const hostKey = "__MOLAB_PLUGIN_HOST_MODULES__";
  const g = globalThis as typeof globalThis & {
    [key: string]: Record<string, Record<string, unknown>>;
  };
  if (!g[hostKey]) g[hostKey] = {};
  g[hostKey][spec] = exports;

  const lines: string[] = [
    `const mod = globalThis[${JSON.stringify(hostKey)}][${JSON.stringify(spec)}];`,
  ];

  const keys = Object.keys(exports).filter((k) => k !== "default" && k !== "__esModule");
  if ("default" in exports) {
    lines.push(`export default mod.default ?? mod;`);
  } else {
    lines.push(`export default mod;`);
  }
  for (const key of keys) {
    if (!/^[A-Za-z_$][\w$]*$/.test(key)) continue;
    lines.push(`export const ${key} = mod[${JSON.stringify(key)}];`);
  }

  const blob = new Blob([lines.join("\n")], { type: "text/javascript" });
  const url = URL.createObjectURL(blob);
  moduleBlobUrls.set(spec, url);
  return url;
}

export async function ensurePluginHostModules(): Promise<PluginHostModules> {
  if (!pluginHostModules) {
    pluginHostModules = getPluginHostModules();
  }
  const modules = pluginHostModules;
  if (importMapReady) return modules;
  for (const [spec, mod] of Object.entries(modules)) {
    buildModuleBlob(spec, mod as unknown as Record<string, unknown>);
  }
  importMapReady = true;
  return modules;
}

async function rewriteBareImports(source: string): Promise<string> {
  const modules = await ensurePluginHostModules();
  const specs = Object.keys(modules);
  let out = source;
  for (const spec of specs) {
    const blobUrl = moduleBlobUrls.get(spec);
    if (!blobUrl) continue;
    const escaped = spec.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    out = out.replace(new RegExp(`(from\\s*)(['"])${escaped}\\2`, "g"), `$1$2${blobUrl}$2`);
    out = out.replace(
      new RegExp(
        `import\\s*\\((\\s*(?:\\/\\*[\\s\\S]*?\\*\\/\\s*|\\/\\/[^\\n]*\\n\\s*)*)(['"])${escaped}\\2`,
        "g",
      ),
      `import($1$2${blobUrl}$2`,
    );
  }
  return out;
}

async function fetchText(url: string): Promise<string> {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) {
    throw new Error(`Failed to fetch ${url}: HTTP ${res.status}`);
  }
  return res.text();
}

const REL_IMPORT_RE = /(from\s*|import\s*\(\s*)(['"])(\.[^'"]+)\2/g;

export async function rewriteModuleGraph(
  url: string,
  owner: string = new URL(url).href,
): Promise<string> {
  const absolute = new URL(url).href;
  let owned = graphChunks.get(owner);
  if (!owned) {
    owned = new Set();
    graphChunks.set(owner, owned);
  }
  owned.add(absolute);

  const cached = rewrittenModuleBlobs.get(absolute);
  if (cached) return cached;

  const inflight = rewriteInFlight.get(absolute);
  if (inflight) return inflight;

  const promise = (async () => {
    rewrittenModuleBlobs.set(absolute, "");

    const source = await fetchText(absolute);
    let rewritten = await rewriteBareImports(source);

    const relSpecs = new Set<string>();
    for (const match of source.matchAll(REL_IMPORT_RE)) {
      relSpecs.add(match[3]);
    }

    const relToBlob = new Map<string, string>();
    await Promise.all(
      [...relSpecs].map(async (rel) => {
        const childAbs = new URL(rel, absolute).href;
        const childBlob = await rewriteModuleGraph(childAbs, owner);
        relToBlob.set(rel, childBlob);
      }),
    );

    rewritten = rewritten.replace(
      REL_IMPORT_RE,
      (full, prefix: string, quote: string, rel: string) => {
        const blob = relToBlob.get(rel);
        if (!blob) return full;
        return `${prefix}${quote}${blob}${quote}`;
      },
    );

    rewritten = `globalThis.__MOLAB_PLUGIN_ENTRY__=${JSON.stringify(absolute)};\n${rewritten}`;

    const blob = new Blob([rewritten], { type: "text/javascript" });
    const blobUrl = URL.createObjectURL(blob);
    rewrittenModuleBlobs.set(absolute, blobUrl);
    return blobUrl;
  })();

  rewriteInFlight.set(absolute, promise);
  try {
    return await promise;
  } finally {
    rewriteInFlight.delete(absolute);
  }
}
