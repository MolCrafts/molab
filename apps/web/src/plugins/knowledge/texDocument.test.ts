import { describe, expect, it } from "@rstest/core";
import { bibliographyName, isTexDocument, withBibliography } from "./texDocument";

describe("isTexDocument", () => {
  it("matches the manuscript suffixes and nothing else", () => {
    expect(isTexDocument("projects/nve-drift/knowledges/nve-drift.tex")).toBe(true);
    expect(isTexDocument("letter.LTX")).toBe(true);
    expect(isTexDocument("projects/nve-drift/knowledges/nve-drift.md")).toBe(false);
    expect(isTexDocument("figures/tab_drift.tex.bak")).toBe(false);
  });
});

describe("withBibliography", () => {
  const source =
    "\\documentclass{article}\n\\begin{document}\n\\bibliography{references}\n\\end{document}\n";

  it("prepends the bibliography as the file the source names", () => {
    const bib = "@misc{evans1990,\n  year = {1990},\n}";
    expect(withBibliography(source, bib)).toBe(
      `\\begin{filecontents*}[overwrite]{references.bib}\n${bib}\n\\end{filecontents*}\n${source}`,
    );
  });

  it("leaves a source with no live bibliography unchanged", () => {
    const commented = "% \\bibliography{references}\n\\begin{document}\\end{document}\n";
    expect(bibliographyName(commented)).toBeNull();
    expect(withBibliography(commented, "@misc{a,}")).toBe(commented);
  });

  it("names the first file of a list, with or without its suffix", () => {
    expect(bibliographyName("\\bibliography{ refs , more }")).toBe("refs");
    expect(bibliographyName("\\bibliography{refs.bib}")).toBe("refs.bib");
  });
});
