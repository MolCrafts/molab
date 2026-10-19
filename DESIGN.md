---
name: molab
description: VS Code Compact scientific operator workbench
colors:
  accent: "#005fb8"
  accent-hover: "#004f9a"
  accent-foreground: "#ffffff"
  accent-muted: "#e8f1fb"
  background: "#ffffff"
  surface-subtle: "#f3f3f3"
  foreground: "#242424"
  muted-foreground: "#616161"
  border: "#e5e5e5"
  input: "#cecece"
  interactive: "#e8e8e8"
  dark-accent: "#60a5fa"
  dark-accent-hover: "#93c5fd"
  dark-accent-foreground: "#0f172a"
  dark-accent-muted: "#172554"
  dark-background: "#1f1f1f"
  dark-surface-subtle: "#181818"
  dark-foreground: "#cccccc"
  dark-muted-foreground: "#a6a6a6"
  dark-border: "oklch(1 0 0 / 10%)"
  dark-input: "oklch(1 0 0 / 12%)"
  dark-interactive: "#303030"
  status-running: "oklch(0.62 0.15 250)"
  status-completed: "oklch(0.6 0.13 150)"
  status-failed: "oklch(0.58 0.19 25)"
  status-warning: "oklch(0.72 0.14 85)"
typography:
  display:
    fontFamily: '"Geist", "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif'
    fontSize: "1.5rem"
    lineHeight: 1.4
  heading:
    fontFamily: '"Geist", "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif'
    fontSize: "1.25rem"
    lineHeight: 1.4
  title:
    fontFamily: '"Geist", "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif'
    fontSize: "1rem"
    lineHeight: 1.4
  body:
    fontFamily: '"Geist", "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif'
    fontSize: "0.8125rem"
    lineHeight: 1.4
  label:
    fontFamily: '"Geist", "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif'
    fontSize: "0.75rem"
    lineHeight: 1.4
  micro:
    fontFamily: '"Geist", "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif'
    fontSize: "0.6875rem"
    lineHeight: 1.4
  mono:
    fontFamily: '"JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace'
rounded:
  hairline: "0.125rem"
  control: "0.375rem"
  panel: "0.5rem"
  overlay: "0.625rem"
spacing:
  hairline: "0.125rem"
  step-1: "0.25rem"
  step-2: "0.5rem"
  step-3: "0.75rem"
  step-4: "1rem"
  step-6: "1.5rem"
  step-8: "2rem"
  icon-sm: "0.875rem"
  icon: "1rem"
  control-compact: "1.75rem"
  control: "2rem"
  control-comfortable: "2.25rem"
  touch-target: "2.75rem"
  row-pad: "0.375rem"
  rail: "9.5rem"
components:
  action-icon:
    textColor: "{colors.foreground}"
    rounded: "{rounded.control}"
    size: "{spacing.control-compact}"
  action-icon-hover:
    backgroundColor: "{colors.interactive}"
    textColor: "{colors.foreground}"
  action-danger:
    textColor: "{colors.status-failed}"
    rounded: "{rounded.control}"
    size: "{spacing.control-compact}"
  input:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    height: "{spacing.control}"
    padding: "0.25rem 0.75rem"
  entity-tab:
    backgroundColor: "{colors.background}"
    textColor: "{colors.muted-foreground}"
    typography: "{typography.label}"
    height: "{spacing.step-8}"
    padding: "0 0.75rem"
  entity-tab-active:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
  tag-category:
    textColor: "{colors.muted-foreground}"
    typography: "{typography.micro}"
    rounded: "{rounded.control}"
    padding: "0 0.5rem"
  dashboard-section:
    backgroundColor: "{colors.background}"
    padding: "0.5rem 0.75rem"
---

# Design System: molab

## Overview

**Creative North Star: "VS Code Compact"**

VS Code Compact is the confirmed visual direction: a precise, quiet, confident scientific operator console. Dashboard, workspace, and settings share neutral surfaces, compact chrome, restrained blue selection and focus, and short operational language. Light is the default; dark is an explicit reading preference.

Density serves browsing, comparison, and recovery. Borderless icon actions keep chrome small; navigation, field choices, status, counts, and scientific meaning retain the text needed to understand them. Keep the existing shared component vocabulary and geometry rather than introducing another visual system.

**Key Characteristics:**
- Compact, connected work surfaces with quiet separators.
- Borderless icon actions with accessible names and hover titles.
- Readable scientific data, explicit state, and restrained selection color.

## Colors

The palette pairs neutral editor surfaces with a restrained blue accent. The frontmatter records source values; `dark-*` entries are theme counterparts, not extra accents. Runtime CSS variables select the correct theme.

### Primary

- **Workbench Blue** (`accent`, `accent-hover`, `accent-foreground`, `accent-muted`): selection, focus, and selected navigation. Use the dark counterparts on dark surfaces.

### Neutral

- **Work Surface** (`background`): the continuous content canvas; surface and canvas aliases share it.
- **Chrome** (`surface-subtle`): the narrow activity rail, titlebar and status band. Explorer bodies, inspectors, entity tabs and table headers share the content canvas.
- **Ink** (`foreground`, `muted-foreground`): data and quieter supporting labels.
- **Dividers and Fields** (`border`, `input`): separate regions or identify editable values without nested boxes.
- **Interaction Wash** (`interactive`): quiet hover and pressed/selected control treatment.

Running, completed, failed, and warning are domain status roles inherited from the constitution. Preserve all remaining existing status roles and their theme-specific foreground/soft variants in CSS; do not substitute the product accent for status. Status always includes words or another non-color cue.

**The Accent Has a Job Rule.** Blue identifies selection and focus; it is not decoration around every section.

## Typography

Use the frontmatter's sans stack throughout the workbench, including primary status percentages and normal numeric cells. Reserve mono for identifiers, hashes, code, raw parameters, and the existing inline Figure measurements. No display-font pairing is introduced. Body and labels carry most of the interface; heading/title/display are available existing scale steps, not a reason to enlarge chrome.

The initial preference is Compact (100% root font size), yielding body text (13px) and labels (12px). The existing 112.5%, 125%, 137.5%, and 150% choices remain available. Stored reading preferences take precedence. Medium section labels and semibold status figures establish hierarchy; preserve tabular numerals.

## Layout

The shell frames a continuous work surface. The titlebar and entity tabs use the existing step-8 (32px); entity/view headers generally occupy 32–36px, with content allowed to determine height. The status band uses step-6 (24px). These are local compact compositions, not changes to the constitution's larger toolbar/statusbar tokens.

Use the existing 4/8/12/16/24/32 spacing ladder. Dense table rows use vertical step-1 (4px); the separately named constitution `row-pad` remains unchanged for components that use it. Dashboard canvases use horizontal step-4 and vertical step-3, with step-4 section spacing. OverviewSheet places an optional full-width lead above a main column and note margin; at the large breakpoint the columns are 2:1, and otherwise stack. Overview instruments progress from one to two to three columns where space permits. Do not manufacture matching tiles.

Allow tables and tab strips to scroll horizontally within their regions. Keep flexible children shrinkable and content scrollable instead of allowing the page to overflow. Settings retain category text beside independently scrolling sections. Coarse-pointer rules expand applicable actions and fields to the touch-target floor (44px); density must not remove keyboard access or recovery controls.

## Elevation & Depth

Workbench surfaces and actions are flat at rest. Tonal changes, connected active tabs, and hairline separators establish hierarchy. Overlays may use the existing theme-specific overlay shadow recorded in the sidecar. Do not apply floating-card shadows to dashboard sections. Existing motion is short state feedback; reduced-motion treatment and essential progress cues remain the implementation's responsibility.

## Shapes

Use hairline corners for dense data, control corners for pressed/typed elements, panel corners where a region needs a boundary, and overlay corners for floating surfaces. Connected entity tabs stay square. Actions have no resting border or shadow; inputs retain a visible field boundary, and metadata tags may retain a quiet outline. Borderless actions do not imply borderless data controls.

## Components

### Buttons

Reuse `WorkbenchAction`, `WorkbenchIconAction`, and the existing retry/dismiss/toggle controls. Icon actions use compact targets (28px) around default icons (16px), with accessible action names and hover titles. Primary, secondary, ghost, and danger workbench actions share the borderless ghost treatment; danger carries semantic destructive text color. Preserve meaningful hover, focus, disabled, and denied states. Navigation and value choices retain their text. App confirmation and cancellation actions use named check/close icons; keep the dialog title and consequence text explicit.

Selection, create, rename, download, delete, refresh and recovery actions use icons only, including notebook tools and dialog submissions. Selection toggles expose their pressed state and name the available action. Execution views omit the invariant `Backend: molq`; show the destination cluster, scheduler and job ID instead.

### Inputs / Fields

Reuse the shared Input and existing parameter/form controls: control height, control radius, body text, quiet input border, and visible focus. Preserve parameter names, types, values, units, and help that changes the user's interpretation. Text-size radio choices remain visibly labeled.

### Navigation

Entity tabs retain text labels on the continuous content canvas, with no vertical tab borders or filled inactive tabs. A short accent underline identifies the active view. Settings categories retain their text and selected wash. The light/dark controls use named sun/moon actions and explicit pressed state; theme and text size are separate per-browser preferences.

Tab switches keep the current content visible while a cold module or data read resolves. Visited tabs retain local state through React Activity; hidden tabs stop effects and polling. Remote data stays in the existing TanStack Query cache. Avoid full-page loading copy, skeleton blocks and entrance animations during tab switches.

Inventory tables use content-colored headers and quiet horizontal separators. A tab already naming the inventory does not need another section heading. Project experiment rows show the name and operational counts on one line; IDs remain available through the name tooltip and the row's copy action. Keep partial-count indicators, while omitting instructions such as “status loads on open”.

### Chips

Reuse `WorkbenchTag`: compact micro text, control corners, quiet outline, and category/metadata/selection or semantic status treatments. Tags describe data; they are not an ornamental badge collection.

### Cards / Containers

`DashboardCard` is a quiet section on the canvas, despite its legacy name. It uses a compact title/count/action row and a small padded body without a new card frame. Reuse `DashboardCanvas`, `InventoryCanvas`, and `OverviewSheet` for connected overview and inventory surfaces.

### Status Overview

`StatusLedger` reuses the shared `ArcChart` from `@molcrafts/ui-vega`. Pair the status mix with explicit counts and the success rate of finished work; show the in-flight explanation when none has finished. Retain “loaded so far” for partial data. Preserve the remote status label `SSH: Arrhenius` when that is the connected host.

## Do's and Don'ts

### Do:
- Do reuse workbench actions, entity tabs, dashboard sections, settings rows, and the shared ArcChart.
- Do retain text for navigation, data choices, status, units, counts, and parameter meaning.
- Do keep retry, dismiss, cancel, and denied-action explanations available.
- Do preserve visible keyboard focus, non-color status cues, tabular numbers, and coarse-pointer targets.

### Don't:
- Don't add nested card scaffolding, decorative gradients, rainbow chrome, or redundant explanatory copy.
- Don't turn navigation and data choices into anonymous icons.
- Don't invent another palette, type scale, or button vocabulary for a new screen.
- Don't present seeded example captures or partial counts as verified live HPC results.

<!-- Sources: apps/web/src/styles/{tailwind,constitution-theme,constitution-base}.css;
apps/web/src/components/workbench/{WorkbenchAction,WorkbenchTag}.tsx;
apps/web/src/app/components/entity/{EntityTabs,Dashboard}.tsx and density.ts;
apps/web/src/app/components/entity/gauges/{Composition,StatusLedger}.tsx;
apps/web/src/components/settings/SettingsShell.tsx; apps/web/src/app/settings/AppearancePanel.tsx;
apps/web/src/lib/{ui-theme,ui-scale}.ts; apps/web/src/app/layout/ContextBar.tsx;
apps/web/src/components/layout/PageHeader.tsx; apps/web/src/components/workbench/WorkbenchStatusStrip.tsx;
../molcrafts-ui/packages/ui/src/components/ui/{button,input,badge}.tsx;
../molcrafts-ui/packages/vega/src/charts.tsx.
Sidecar tonal ramps are synthesized preview metadata, not application palette additions.
Evidence: .impeccable/review/*.png are authorized local seeded examples, not live Arrhenius verification.
Production build acceptance remains outside this visual record: preexisting external molvis/molrs interface mismatch.
-->
