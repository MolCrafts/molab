/**
 * Install TeXlyre BusyTeX assets once.
 *
 * The published archive is the whole TeX Live 2026 set (~522 MB). This keeps
 * the combined engine and texlive-basic (~125 MB) under public/busytex/.
 * A second run does nothing when those files already match. Packages outside
 * the basic set are not stored; the preview fetches them on demand.
 */
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { mkdir, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const ARCHIVE_URL =
  "https://github.com/TeXlyre/texlyre-busytex/releases/download/assets-v1.4.0/busytex-assets.tar.gz";
const ARCHIVE_SHA256 = "1caa434fb5aab5bdd59dc303bca2ac7b9b9af02ef1627bf8652caabfa1b7cd2b";

/** Basename inside `busytex/` → sha256 of the file we keep. */
const FILES = {
  "busytex_biber.js": "e1a3ff55a120e392d3a7ef27f1bff1978c7a9d5978999296e39e1cfeac01d923",
  "busytex_pipeline.js": "4855e8fec24e8df952e1080d902791752bcdf283f4fae15811c371dd3ba3389e",
  "busytex_worker.js": "80eca56a2eb015bdfbebff26e539dd793407b73b6c1cd351170e6fdb6e17c39a",
  "busytex.js": "875b87795162cb26b15bd93cffa2e8739bcb900d623ab904029b39402508a1a4",
  "busytex.wasm": "8d1988fc58cd1611c3cbd6bd986c3e607e5ff44f1d94252207ff7aae4cee72e0",
  "texlive-basic.js": "d4abc2e93a1ae33099107c6ad8a61813978cd44036a95697db2f2365a393c283",
  "texlive-basic.data": "ccb35d98d77cbaf988e1481f8538709f72166196785cf6b8785eabe6c8fb2993",
};

const dest = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../public/busytex");

const sha256 = (file) =>
  new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    createReadStream(file)
      .on("error", reject)
      .on("data", (chunk) => hash.update(chunk))
      .on("end", () => resolve(hash.digest("hex")));
  });

const run = (command, args) =>
  new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "inherit" });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} exited ${code}`));
    });
  });

const installed = async () => {
  for (const [name, expected] of Object.entries(FILES)) {
    const file = path.join(dest, name);
    try {
      await stat(file);
    } catch {
      return false;
    }
    if ((await sha256(file)) !== expected) return false;
  }
  return true;
};

if (await installed()) {
  console.log(`BusyTeX assets already installed in ${dest}`);
  process.exit(0);
}

await mkdir(dest, { recursive: true });
const archive = path.join(tmpdir(), "busytex-assets-v1.4.0.tar.gz");
console.log(`Downloading ${ARCHIVE_URL}`);
await run("curl", ["-L", "--fail", "--retry", "3", "--continue-at", "-", "-o", archive, ARCHIVE_URL]);
const archiveHash = await sha256(archive);
if (archiveHash !== ARCHIVE_SHA256) {
  throw new Error(`archive sha256 ${archiveHash} does not match ${ARCHIVE_SHA256}`);
}

const members = Object.keys(FILES).map((name) => `busytex/${name}`);
await run("tar", ["-xzf", archive, "-C", path.dirname(dest), ...members]);
await rm(archive, { force: true });

if (!(await installed())) {
  throw new Error(`extracted files in ${dest} do not match assets-v1.4.0`);
}
console.log(`BusyTeX assets ready in ${dest}`);
