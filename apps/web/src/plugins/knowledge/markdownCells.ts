/** Split / join a markdown document into Notion-style cells (top-level blocks). */

const FENCE = /^```/;
const HEADING = /^#{1,6}\s/;

/**
 * Break *source* into cells: a heading, a paragraph, a list, or a fenced
 * code block. Blank lines separate cells. Fences stay intact.
 */
export function splitMarkdownCells(source: string): string[] {
  const text = source.replace(/\r\n?/g, "\n");
  if (text.trim().length === 0) return [""];
  const cells: string[] = [];
  let buf: string[] = [];
  let inFence = false;
  const flush = (): void => {
    const cell = buf.join("\n").replace(/^\n+/, "").replace(/\n+$/, "");
    buf = [];
    if (cell.length > 0) cells.push(cell);
  };
  for (const line of text.split("\n")) {
    if (FENCE.test(line)) {
      if (!inFence && buf.length > 0) flush();
      inFence = !inFence;
      buf.push(line);
      if (!inFence) flush();
      continue;
    }
    if (inFence) {
      buf.push(line);
      continue;
    }
    if (line.trim() === "") {
      flush();
      continue;
    }
    if (HEADING.test(line)) {
      if (buf.length > 0) flush();
      buf.push(line);
      flush();
      continue;
    }
    buf.push(line);
  }
  flush();
  return cells.length > 0 ? cells : [""];
}

/** Reassemble cells into a markdown document. Empty cells are dropped. */
export function joinMarkdownCells(cells: readonly string[]): string {
  return cells
    .map((cell) => cell.replace(/\r\n?/g, "\n").replace(/\n+$/, "").trimEnd())
    .filter((cell) => cell.length > 0)
    .join("\n\n");
}
