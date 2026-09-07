/**
 * Shared host modules for plugin import-map injection.
 *
 * The specifier list is {@link PluginHostModuleId} in
 * `@molcrafts/molexp-plugin`. This map must inject every id on that list, and
 * nothing else — `satisfies` below enforces both directions at compile time.
 */

import type { PluginHostModuleId } from "@molcrafts/molexp-plugin";
import * as MolexpPlugin from "@molcrafts/molexp-plugin";
import * as MolexpPluginUi from "@molcrafts/molexp-plugin/ui";
import * as React from "react";
import * as JsxDevRuntime from "react/jsx-dev-runtime";
import * as JsxRuntime from "react/jsx-runtime";
import * as ReactDOM from "react-dom";
import * as ReactDOMClient from "react-dom/client";

export type { PluginHostModuleId } from "@molcrafts/molexp-plugin";

export const pluginHostModules = {
  react: React,
  "react-dom": ReactDOM,
  "react-dom/client": ReactDOMClient,
  "react/jsx-runtime": JsxRuntime,
  "react/jsx-dev-runtime": JsxDevRuntime,
  "@molcrafts/molexp-plugin": MolexpPlugin,
  "@molcrafts/molexp-plugin/ui": MolexpPluginUi,
} as const satisfies Record<PluginHostModuleId, unknown>;

export type PluginHostModules = typeof pluginHostModules;

export function getPluginHostModules(): PluginHostModules {
  return pluginHostModules;
}
