/** The first rows of a CSV / TSV, for the asset preview (L08). Not a full CSV reader. */

export interface TablePreview {
  header: string[];
  rows: string[][];
  /** Data rows in the text read (the file may hold more). */
  totalRows: number;
  /** The text ended mid-file, so `totalRows` is a lower bound. */
  partial: boolean;
}

/** Split one line on `delimiter`, honouring double-quoted fields. */
export const splitDelimited = (line: string, delimiter: string): string[] => {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (quoted) {
      if (char === '"' && line[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else if (char === '"') quoted = false;
      else cell += char;
    } else if (char === '"') quoted = true;
    else if (char === delimiter) {
      cells.push(cell);
      cell = "";
    } else cell += char;
  }
  cells.push(cell);
  return cells;
};

export const delimiterFor = (name: string, firstLine: string): string => {
  if (/\.tsv$/i.test(name)) return "\t";
  const tabs = firstLine.split("\t").length;
  const commas = firstLine.split(",").length;
  return tabs > commas ? "\t" : ",";
};

export const parseTablePreview = (
  text: string,
  name: string,
  maxRows: number,
  partial = false,
): TablePreview => {
  const lines = text.split(/\r?\n/);
  // A cut-off read ends mid-line: drop the last, unfinished one.
  if (partial) lines.pop();
  const filled = lines.filter((line) => line.trim() !== "");
  const [first = "", ...rest] = filled;
  const delimiter = delimiterFor(name, first);
  return {
    header: splitDelimited(first, delimiter),
    rows: rest.slice(0, maxRows).map((line) => splitDelimited(line, delimiter)),
    totalRows: rest.length,
    partial,
  };
};
