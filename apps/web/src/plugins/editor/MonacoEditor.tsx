import { lazyWithPrefetch } from "@/lib/lazy-with-prefetch";

/** Sole Monaco entry for apps/web. Capability vendor stays inside this plugin. */
export const MonacoEditor = lazyWithPrefetch(() => import("@monaco-editor/react"));
