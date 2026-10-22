/**
 * Geometry and colour token contract.
 *
 * The `/mol:ui` `tokens` stage is only done while it stays done: every check
 * here was a live drift at some point, and each one is cheap to reintroduce by
 * typing a number instead of a token name. Scans source text on purpose — the
 * failure mode is a literal in a `className`, which no type or render test
 * sees.
 */

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "@rstest/core";

const here = dirname(fileURLToPath(import.meta.url));
const srcRoot = resolve(here, "..");
const sourceFiles = (dir: string, out: string[] = []): string[] => {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "generated" || entry.name === "node_modules") continue;
      sourceFiles(full, out);
      continue;
    }
    // Tests carry fixture colours and assertion strings, and render nothing.
    if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) out.push(full);
  }
  return out;
};

const files = sourceFiles(srcRoot).map((path) => ({
  path: relative(srcRoot, path),
  text: readFileSync(path, "utf8"),
}));

const hits = (pattern: RegExp): string[] =>
  files.flatMap((file) =>
    file.text
      .split("\n")
      .flatMap((line, index) =>
        pattern.test(line) ? [`${file.path}:${index + 1} ${line.trim()}`] : [],
      ),
  );

const CONSTITUTION = resolve(here, "constitution-theme.css");
const PRODUCT_TOKENS = resolve(here, "tailwind.css");
/** Shared source of the constitution layer, when the sibling checkout exists. */
const REGISTRY_SOURCE = resolve(
  here,
  "../../../../../molcrafts-ui/src/styles/constitution-theme.css",
);

/** First name segment of each token in a namespace — the *role* it claims. */
const claimedRoles = (css: string, namespace: string): Set<string> => {
  const roles = new Set<string>();
  const pattern = new RegExp(`^\\s*--${namespace}-([a-z0-9]+)`, "gm");
  for (const match of css.matchAll(pattern)) if (match[1]) roles.add(match[1]);
  return roles;
};

const declaredKeys = (css: string): Map<string, string> => {
  const keys = new Map<string, string>();
  for (const line of css.split("\n")) {
    const match = /^\s*(--(?:text|radius|spacing|font|ease|shadow)[a-z0-9-]*)\s*:\s*([^;]+);/.exec(
      line,
    );
    if (match?.[1] && match[2]) keys.set(match[1], match[2].trim());
  }
  return keys;
};

const SPACING_UTILITIES = "space-x|space-y|gap-x|gap-y|gap|px|py|pt|pb|pl|pr|p|mx|my|mt|mb|ml|mr|m";

describe("geometry tokens", () => {
  it("keeps every spacing step on the 4·8·12·16·24·32 ladder", () => {
    // 0.5 (2px), 1.5 (6px), 2.5 (10px), 5 (20px) and 10 (40px) are off the
    // constitution's ladder. The two deliberate sub-grid values are named
    // tokens (`gap-hairline`, `py-row-pad`) and so do not match this.
    expect(
      hits(
        new RegExp(
          `(?:^|["'\`\\s:])(?:${SPACING_UTILITIES})-(?:0\\.5|1\\.5|2\\.5|5|10)(?![\\w.[/-])`,
        ),
      ),
    ).toEqual([]);
  });

  it("names pixel geometry instead of spelling it in an arbitrary value", () => {
    // Percentages, viewport units, calc(), ch and CSS custom properties stay —
    // they are relationships, not constants. A raw px is a constant with no name.
    expect(
      hits(
        /(?:^|["'`\s:])(?:min-|max-)?(?:h|w|size|rounded|top|left|right|bottom|inset)-\[[\d.]+px\]/,
      ),
    ).toEqual([]);
  });

  it("keeps control heights inside the constitution's bands", () => {
    // h-11 (44px) and taller on an input/button; the toolbar band owns 40–48px
    // through `h-toolbar` / `h-toolbar-compact`, not a raw step.
    expect(hits(/(?:^|["'`\s:])h-(?:11|12|13|14)(?![\w.[/-])/)).toEqual([]);
  });
});

describe("colour tokens", () => {
  it("keeps literal colours out of feature code", () => {
    expect(hits(/(?:^|["'`\s:(])(?:#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\()/)).toEqual([]);
  });

  it("keeps raw Tailwind palette utilities out of feature code", () => {
    const palette =
      "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
    expect(
      hits(
        new RegExp(
          `(?:^|["'\`\\s:])(?:bg|text|border|ring|fill|stroke|from|to|via)-(?:${palette})-\\d{2,3}\\b`,
        ),
      ),
    ).toEqual([]);
  });
});

describe("one source per token", () => {
  it("never redefines a constitution key in the product layer", () => {
    // `constitution-theme.css` is vendored from molcrafts-ui; shadowing one of
    // its keys here means the value has two homes and can drift in silence.
    const constitution = declaredKeys(readFileSync(CONSTITUTION, "utf8"));
    const product = declaredKeys(readFileSync(PRODUCT_TOKENS, "utf8"));
    expect([...product.keys()].filter((key) => constitution.has(key))).toEqual([]);
  });

  it("keeps the vendored constitution byte-identical to its source", () => {
    // Skipped when the sibling checkout is absent (CI clones molab alone);
    // locally this is what catches a hand-edit of a synced file — which is how
    // `--spacing-statusbar` came to be 22px here and 28px upstream.
    if (!existsSync(REGISTRY_SOURCE)) return;
    expect(readFileSync(CONSTITUTION, "utf8")).toEqual(readFileSync(REGISTRY_SOURCE, "utf8"));
  });
});

describe("the product consumes the vocabulary, it does not extend it", () => {
  // A product that needs a new role has found a gap in the constitution, and
  // the fix is to widen the constitution — not to grow a second vocabulary
  // downstream that later has to be reconciled. Product tokens name *product
  // layout* (panel widths, chart heights, viewport caps); the constitution
  // names control geometry, and it names it for everyone.
  it.each(["spacing", "radius"])("claims no --%s role the constitution owns", (namespace) => {
    const constitution = claimedRoles(readFileSync(CONSTITUTION, "utf8"), namespace);
    const product = claimedRoles(readFileSync(PRODUCT_TOKENS, "utf8"), namespace);
    expect([...product].filter((role) => constitution.has(role)).sort()).toEqual([]);
  });

  it("registers every constitution geometry role with the class merger", () => {
    // `cn()` merges by class group; a token name it does not know is a token
    // whose two values both survive the merge. Silent, and only visible as a
    // component that ignores an override.
    const merger = readFileSync(resolve(here, "../lib/utils.ts"), "utf8");
    const constitution = readFileSync(CONSTITUTION, "utf8");
    // Stock Tailwind scale names (radius-sm/md/lg/xl) are already class groups.
    const STOCK = new Set(["xs", "sm", "md", "lg", "xl", "2xl", "3xl", "full", "none"]);
    const missing = [...declaredKeys(constitution).keys()]
      .filter((key) => key.startsWith("--spacing-") || key.startsWith("--radius-"))
      .map((key) => key.replace(/^--(?:spacing|radius)-/, ""))
      .filter((name) => !STOCK.has(name) && !merger.includes(`"${name}"`));
    expect(missing).toEqual([]);
  });
});
