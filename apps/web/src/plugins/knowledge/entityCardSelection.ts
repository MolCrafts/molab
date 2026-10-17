import type { EntityCard } from "@/api/generated/models/EntityCard";
import type { Selection } from "@/app/types";

/**
 * Map an embedded-entity card onto the navigation selection that opens it.
 * A missing card and a legacy path card are not navigable. Runs, experiments,
 * and known assets open by id. References and notes open by bundle path.
 */
export const toSelection = (card: EntityCard, assetIds: ReadonlySet<string>): Selection | null => {
  if (card.missing) return null;
  switch (card.kind) {
    case "run":
      return { objectType: "run", objectId: card.id };
    case "experiment":
      return { objectType: "experiment", objectId: card.id };
    case "asset":
      if (assetIds.has(card.id)) return { objectType: "asset", objectId: card.id };
      return card.relPath ? { objectType: "knowledge", objectId: card.relPath } : null;
    case "path":
      return null;
    case "reference":
    case "note":
      return card.relPath ? { objectType: "knowledge", objectId: card.relPath } : null;
    default:
      return card.relPath ? { objectType: "knowledge", objectId: card.relPath } : null;
  }
};
