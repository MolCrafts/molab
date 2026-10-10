import type { PluginAPI } from "@molcrafts/molab-plugin";
import { BookOpen } from "lucide-react";
import type { NavigationContribution } from "@/app/navigation/sections";
import { lazyWithPrefetch } from "@/lib/lazy-with-prefetch";

const KnowledgeExplorer = lazyWithPrefetch(() =>
  import("./KnowledgeExplorer").then((module) => ({
    default: module.KnowledgeExplorer,
  })),
);

export const KNOWLEDGE_NAVIGATION: NavigationContribution = {
  id: "knowledge",
  label: "Knowledge",
  explorerTitle: "Knowledge",
  breadcrumbLabel: "Knowledge",
  icon: BookOpen,
  route: "/knowledge",
  placement: "primary",
  order: 50,
  shellMode: "explorer",
  explorer: KnowledgeExplorer,
  emptySelection: {
    title: "No document selected",
    description: "Choose a note from the explorer, or create a new one.",
  },
  retainSelectionFor: ["knowledge"],
  matches: (pathname) => pathname.startsWith("/knowledge"),
};

export const registerKnowledgeNavigation = (api: PluginAPI): void => {
  const spec = KNOWLEDGE_NAVIGATION;
  api.views.registerContainer({
    id: spec.id,
    title: spec.label,
    icon: spec.icon,
    placement: spec.placement,
    order: spec.order,
  });
  api.views.register({
    id: spec.id,
    container: spec.id,
    title: spec.explorerTitle,
    breadcrumbLabel: spec.breadcrumbLabel,
    route: spec.route,
    shellMode: spec.shellMode,
    order: spec.order,
    explorer: spec.explorer,
    landing: spec.landing,
    emptySelection: spec.emptySelection,
    retainSelectionFor: spec.retainSelectionFor,
    matches: spec.matches,
  });
};
