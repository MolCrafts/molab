import { describe, expect, it } from "@rstest/core";
import {
  DEFAULT_TAIL,
  excerptLines,
  isErrorLine,
  parseLineRange,
  streamOfFile,
} from "./logExcerpt";

describe("parseLineRange", () => {
  it("reads a range and a single line", () => {
    expect(parseLineRange("1182-1185")).toEqual({ from: 1182, to: 1185 });
    expect(parseLineRange(" 3 – 4 ")).toEqual({ from: 3, to: 4 });
    expect(parseLineRange("7:9")).toEqual({ from: 7, to: 9 });
    expect(parseLineRange("1184")).toEqual({ from: 1184, to: 1184 });
  });

  it("refuses a reversed, zero or malformed range", () => {
    expect(parseLineRange("5-2")).toBeNull();
    expect(parseLineRange("0-2")).toBeNull();
    expect(parseLineRange("a-b")).toBeNull();
    expect(parseLineRange("")).toBeNull();
    expect(parseLineRange(undefined)).toBeNull();
  });
});

describe("streamOfFile", () => {
  it("maps the three log files to their streams", () => {
    expect(streamOfFile("run.log")).toBe("run");
    expect(streamOfFile("stdout.log")).toBe("stdout");
    expect(streamOfFile("stderr.log")).toBe("stderr");
    expect(streamOfFile("out/md/log.lammps")).toBeNull();
  });
});

describe("excerptLines", () => {
  const text = ["step 1", "step 2", "ERROR: drift", "Traceback (most recent call last):", ""].join(
    "\n",
  );

  it("numbers the lines of a range and marks error lines", () => {
    expect(excerptLines(text, { from: 2, to: 4 })).toEqual([
      { number: 2, text: "step 2", error: false },
      { number: 3, text: "ERROR: drift", error: true },
      { number: 4, text: "Traceback (most recent call last):", error: true },
    ]);
  });

  it("clips a range past the end and drops the trailing empty line", () => {
    expect(excerptLines(text, { from: 4, to: 99 }).map((line) => line.number)).toEqual([4]);
    expect(excerptLines(text, { from: 9, to: 12 })).toEqual([]);
  });

  it("shows the tail when no range is written", () => {
    const long = Array.from({ length: 40 }, (_, index) => `line ${index + 1}`).join("\n");
    const tail = excerptLines(long, null);
    expect(tail).toHaveLength(DEFAULT_TAIL);
    expect(tail[0]?.number).toBe(40 - DEFAULT_TAIL + 1);
    expect(tail.at(-1)?.text).toBe("line 40");
  });

  it("matches error words in any case", () => {
    expect(isErrorLine("RuntimeException raised")).toBe(true);
    expect(isErrorLine("all good")).toBe(false);
  });
});
