/**
 * Ask the shell to load part of the entity hierarchy (experiments of a
 * project, runs of an experiment) — the same lazy loads the tree's expand
 * triggers. A page that names entities it did not navigate to (a knowledge
 * document's hosts and refs, L10) uses it. Outside the shell it does nothing.
 */

import { createContext, useContext } from "react";

export interface EntityExpansion {
  expandProject: (projectId: string) => void;
  expandExperiment: (projectId: string, experimentId: string) => void;
  isProjectExpanded: (projectId: string) => boolean;
  isExperimentExpanded: (projectId: string, experimentId: string) => boolean;
}

const NONE: EntityExpansion = {
  expandProject: () => undefined,
  expandExperiment: () => undefined,
  isProjectExpanded: () => true,
  isExperimentExpanded: () => true,
};

const EntityExpansionContext = createContext<EntityExpansion>(NONE);

export const EntityExpansionProvider = EntityExpansionContext.Provider;

export const useEntityExpansion = (): EntityExpansion => useContext(EntityExpansionContext);
