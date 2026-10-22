/**
 * Tab title for a file-type plugin contribution.
 *
 * When ``usesCatalogBadge`` is true, ``catalogCount`` is the tile/series count
 * (e.g. molplot scalars) — never the matched-file count. Otherwise the label
 * shows the matched-file count only when more than one file matched.
 */
export const pluginTabLabel = (
  label: string,
  fileCount: number,
  usesCatalogBadge: boolean,
  catalogCount?: number | null,
): string => {
  if (usesCatalogBadge) {
    if (catalogCount == null) return label;
    return `${label} (${catalogCount})`;
  }
  if (fileCount <= 1) return label;
  return `${label} (${fileCount})`;
};
