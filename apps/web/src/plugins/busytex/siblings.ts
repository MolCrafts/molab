export type ManuscriptFile = {
  /** Path written next to the main file for the engine. */
  enginePath: string;
  /** Workspace-relative path to read. */
  workspacePath: string;
  binary: boolean;
};

const GRAPHIC_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"] as const;

const isSafeRelative = (rel: string): boolean => {
  if (rel.length === 0 || rel.startsWith("/") || rel.includes("\\")) return false;
  return rel.split("/").every((part) => part.length > 0 && part !== "." && part !== "..");
};

const directoryOf = (texPath: string): string => {
  const slash = texPath.lastIndexOf("/");
  return slash >= 0 ? texPath.slice(0, slash + 1) : "";
};

const stemOf = (texPath: string): string => {
  const base = texPath.split("/").pop() ?? "main";
  return base.replace(/\.(tex|ltx)$/i, "") || "main";
};

/**
 * Files a manuscript names beside its main source: bibliography, a compiled
 * `.bbl` when one sits next to the `.tex`, `\input` fragments, and figures.
 * The engine always compiles as `main.tex`, so the `.bbl` is staged as
 * `main.bbl`. A host TeX tree is not consulted.
 */
export const manuscriptFiles = (source: string, texPath: string): ManuscriptFile[] => {
  if (!texPath || !isSafeRelative(texPath)) return [];
  const directory = directoryOf(texPath);
  const files: ManuscriptFile[] = [];
  const seen = new Set<string>();

  const add = (enginePath: string, binary: boolean): void => {
    if (!isSafeRelative(enginePath) || seen.has(enginePath)) return;
    seen.add(enginePath);
    files.push({
      enginePath,
      workspacePath: `${directory}${enginePath}`,
      binary,
    });
  };

  for (const match of source.matchAll(/\\addbibresource\{([^}]+)\}/g)) {
    add(match[1].trim(), false);
  }
  add(`${stemOf(texPath)}.bbl`, false);

  for (const match of source.matchAll(/\\csname @@input\\endcsname\s+(\S+)/g)) {
    add(match[1].trim(), false);
  }
  for (const match of source.matchAll(/\\input\{([^}]+)\}/g)) {
    const name = match[1].trim();
    add(name.endsWith(".tex") ? name : `${name}.tex`, false);
  }

  const prefixes = [...source.matchAll(/\\graphicspath\{\{([^}]+)\}\}/g)].map((match) =>
    match[1].trim(),
  );
  const roots = prefixes.length > 0 ? prefixes : [""];
  for (const match of source.matchAll(/\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}/g)) {
    const name = match[1].trim();
    const named = /\.(pdf|png|jpe?g)$/i.test(name)
      ? [name]
      : GRAPHIC_EXTENSIONS.map((ext) => name + ext);
    for (const root of roots) {
      for (const file of named) {
        add(`${root}${file}`.replace(/\/{2,}/g, "/"), true);
      }
    }
  }

  // The staged bibliography has to match the engine's job name.
  return files.map((file) =>
    file.enginePath.endsWith(".bbl") ? { ...file, enginePath: "main.bbl" } : file,
  );
};
