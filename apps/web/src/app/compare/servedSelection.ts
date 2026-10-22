/** Compare rows that belong to a workspace this serve is actually hosting. */
export const compareEntriesForWorkspaces = <T extends { ref: { workspaceKey: string } }>(
  entries: readonly T[],
  workspaceKeys: readonly string[],
): T[] => {
  if (workspaceKeys.length === 0) return [];
  const keys = new Set(workspaceKeys);
  return entries.filter((entry) => keys.has(entry.ref.workspaceKey));
};
