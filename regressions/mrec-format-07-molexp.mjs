#!/usr/bin/env node
/**
 * mrec-format-07-molexp — molvis filename-gate contract (hard-coded goldens).
 *
 * Provenance: public predicates in apps/web/src/plugins/molvis/openable.ts
 * (`isMolvisZarr` / `uniqueMolvisFiles` / `zarrStoreRoot`). Spec
 * `.claude/specs/mrec-format-07-molexp.md`, 2026-08-30. Not a third-party
 * oracle — literals are the web plugin matcher contract.
 * Run via `npx tsx regressions/mrec-format-07-molexp.mjs`.
 */
import assert from "node:assert/strict";
import {
  isMolvisZarr,
  uniqueMolvisFiles,
  zarrStoreRoot,
} from "../apps/web/src/plugins/molvis/openable.ts";

const file = (relPath) => ({
  name: relPath.split("/").pop() ?? relPath,
  relPath,
});

assert.equal(isMolvisZarr(file("growth.mrec")), true);
assert.equal(isMolvisZarr(file("growth.mrec/zarr.json")), true);
assert.equal(isMolvisZarr(file("growth.mrec.zip")), false);
assert.equal(isMolvisZarr(file("growth.zarr")), false);
assert.equal(isMolvisZarr(file("metrics.mlp.zarr")), false);
assert.equal(isMolvisZarr(file("artifacts/pkg/frame/zarr.json")), false);
assert.equal(isMolvisZarr(file("artifacts/pkg/trajectory/zarr.json")), false);
assert.equal(isMolvisZarr(file("artifacts/pkg/meta/zarr.json")), false);

assert.equal(zarrStoreRoot("foo.mrec/zarr.json"), "foo.mrec");

const collapsed = uniqueMolvisFiles([
  file("artifacts/growth.mrec/trajectory/zarr.json"),
  file("artifacts/growth.mrec/meta/zarr.json"),
  file("traj.xyz"),
]);
assert.deepEqual(
  collapsed.map((f) => f.name),
  ["growth.mrec", "traj.xyz"],
);

console.log("mrec-format-07-molexp: ok");
