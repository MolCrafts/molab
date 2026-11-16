/**
 * Stand-in for `@molcrafts/ui/file-tree` when the sibling `molcrafts-ui`
 * checkout is absent. A paths entry aimed at the published `.js` hides its
 * `.d.ts`, and one aimed at the `.d.ts` makes the test bundler execute types.
 * This file is real TypeScript; the `.js` import is what runs.
 */
export {
  buildFileTree,
  collectFolderIds,
  type FileTreeNode,
  type FlatFile,
} from "../../../../node_modules/@molcrafts/ui/dist/lib/file-tree.js";
