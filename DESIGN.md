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

Use the existing 4/8/12/16/24/32 spacing ladder. Dense table rows use vertical step-1 (4px); the separately named constitution `row-pad` remains unchanged for components that use it. Dashboard canvases use horizontal step-4 and vertical step-3, with step-4 section spacing. OverviewSheet places an optional full-width lead above a main column and note margin; at the large breakpoint the columns are 2:1, and otherwise stack. Every Overview tab — workspace Dashboard, project, experiment, run, asset and workflow — sits in one frame (`OverviewCanvas`): centred at `max-w-6xl` on a step-4 canvas margin that widens to step-8 from the small breakpoint with step-12 (48px) between sections: an instrument strip whose cells (step-6 padding) run one column, then two at the small breakpoint, then one column per cell at the extra-large breakpoint (a leading dial cell 1.4 times the others), so a three-gauge strip never leaves a hole; the activity panel at full width; the per-child and backend breakdowns at 3:2 from the large breakpoint, a step-16 gutter between; and the duration chart at full width. The Attention and Timeline tabs centre at the same width. Air is the separator: do not manufacture matching tiles or fill the width for its own sake.

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

The entity tab list is start-aligned and does not shrink. It scrolls horizontally with its scrollbar hidden, and the active tab is scrolled into view. The workspace Dashboard is a fixed page with Overview, Attention (count) and Timeline tabs. Project tabs are Overview, Experiments (count), Attention (count), Timeline, Assets and Settings. A tab's count appears only when it is non-zero.

Inventory tables use content-colored headers and quiet horizontal separators. A tab already naming the inventory does not need another section heading. The Attention tab is a flat list of failed and cancelled runs between quiet rules, and each row shows a status dot and word, the run name, project · experiment, and its relative age. The Timeline tab is the run schedule, newest first. Project experiment rows show the name and operational counts on one line; IDs remain available through the name tooltip and the row's copy action. Keep partial-count indicators, while omitting instructions such as “status loads on open”.

### Chips

Reuse `WorkbenchTag`: compact micro text, control corners, quiet outline, and category/metadata/selection or semantic status treatments. Tags describe data; they are not an ornamental badge collection.

### Cards / Containers

`DashboardCard` is a quiet section on the canvas, despite its legacy name. It uses a compact title/count/action row and a small padded body without a new card frame. It remains for settings and detail sections, such as project Settings, asset, workflow and scheduler tabs. The workspace and project Overviews do not use it. Their gauges sit in `Gauge`: a hairline rule above, a medium label on the left and a right-aligned muted readout, with no frame. Reuse `DashboardCanvas`, `InventoryCanvas`, and `OverviewSheet` for connected overview and inventory surfaces.

### Status Overview

The workspace Dashboard, the project Overview and the experiment Overview render one shared `ExecutionOverview`; the experiment groups by a swept parameter (only parameters whose value differs between its runs) with a pressed choice beside the heading. **The One Run Is a Story Rule.** A run is one point of a sweep, so its Overview carries no rollup gauges — a success rate or a status mark over one item only repeats its status. It shares the frame, not the strip. It leads with a verdict sentence in status ink at display size (“Failed at Train model after 48m”, “Running Train model · 1h 32m so far”), the task count done and the attempt's place (“attempt 2 of 2, a rerun”), the attempt's own error, and icon actions to its logs and execution. Then the latest attempt's tasks on a `TimelineChart` from the journal's `started_at` / `finished_at` (click inspects the task); then, side by side, the run among its experiment's finished runs on a `PositionChart` (the run ringed and labelled, a live run placed at its elapsed time, the readout ranking it) with the parameters that set it apart, and the attempt's scalar results as figures. An attempts timeline appears only when there is more than one attempt. Attempts are named by order and mode (“#2 · resume”), never by id. The asset Overview counts versions, the latest size and its change, and origins, over a vertical `CountBars` of size by version; the workflow Overview shows task state, the task count and the most common type over `CountBars` of tasks by type, and its task table moved to a Tasks tab. Section headings are `GaugeSection`. It opens with an `InstrumentStrip`: one band with a top and bottom hairline and hairline dividers between cells, and no card frames. Each `Instrument` cell has a label, a title-size semibold figure, and a one-line caption naming its unit (executions or runs), followed by a drawn face.

**The Gauge Opens Its List Rule.** An instrument that summarises a list is a button that opens that list's tab. It shows a persistent “Timeline ›” or “List ›” hint at rest. The list itself lives behind the tab.

**The Symbols Over Sentences Rule.** On a dashboard a count is an icon and a number (`Tally`, `StatusTally`, `StatusTallies`), a status is its status icon (shape and colour), and a key is icons (`StatusGlyphLegend`, `DialLegend`'s icon rows and Σ basis). The sentence each would have said is its hover title and accessible name, never printed text. No instruction copy (“click to open”, “drag to filter”): pointer, hover and a single icon carry it. A jump to a tab is an arrow icon titled with the tab's name. Navigation tabs and section titles keep short words.

**The One Gesture Grammar Rule.** Every Overview chart is a Vega-Lite view (`@molcrafts/ui-vega-lite`, specs in `gauges/vega/`) and answers the same gestures. Hover keeps the mark — or its whole row or bucket — at full ink, recedes the rest to 0.32, and shows a one-sentence tooltip. Click opens what the mark stands for: a run, a project or experiment, the Attention tab for a failed or cancelled dial segment. Two charts filter the rest of the Overview: drag a window across Activity, or click a backend (click again to release it). A filter strip above the instruments names what is applied, how many runs remain, and clears it. A held backend stays at full ink while its peers stay receded. Click is a view listener, not a point selection, so a second click on the same mark still registers. Colours reach Vega resolved from the status ramp, never as `var()`.

- **SuccessDial**: a 240° arc of finished outcomes only (completed, failed, cancelled). Completed starts at the dial's zero, so its end is the success rate, read against quarter ticks. A sans tabular legend counts each outcome and the finished total. Active work never enters the arc, and with nothing finished the dial shows the in-flight count instead.
- **UnitMeter**: one mark per item (a 15px column), each naming its run and age on hover and opening it on click. In-flight marks fill with elapsed time against twice the median run, and a median reference rule sits at half height. Queued marks are outlines. Attention marks run newest first, with an age line under the meter (“16m → 6h ago”). Marks beyond capacity fold into “+N”. An empty meter is a dashed track with its words.
- **DurationRange**: on the shared span scale, a whisker from fastest to slowest, an accent-tinted box for the middle half and a median rule.

Below the strip, `ActivityChart` draws starts above the axis and finishes below it, stacked by outcome, with a 24h/7d pressed toggle. Started bars are muted ink at 45%, and finishes carry status. Two `MixChart`s follow, one by project or experiment and one by backend: a normalised bar per group, segments in status order, the total and failure share printed past the end in failed ink when non-zero. `DurationDots` closes the page: one dot per finished run on a shared duration axis (logarithmic past a 20× spread), a band for the middle half and a rule for the median per child. The Timeline tab is `TimelineChart`, one bar per run on one clock with a dashed rule at now. Experiment pages still use the HTML encodings (`StatusBreakdown`, `DurationStrip`, `Schedule`).

**The Outlined Queue Rule.** Wherever queued appears in a status mix (distribution segment, legend dot, unit mark), draw it as an outline, never a fill. That is its non-color cue apart from cancelled grey.

`StatusLedger` still reuses the shared `ArcChart` from `@molcrafts/ui-vega`, and it now leads only the experiment and run overviews. Pair the status mix with explicit counts and the success rate of finished work; show the in-flight explanation when none has finished. Retain “loaded so far” for partial data. Preserve the remote status label `SSH: Arrhenius` when that is the connected host.

## Do's and Don'ts

### Do:
- Do reuse workbench actions, entity tabs, dashboard sections, settings rows, the shared Overview gauges, and the shared ArcChart where StatusLedger leads an experiment or run overview.
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
apps/web/src/app/components/entity/gauges/{Composition,StatusLedger,Gauge,InstrumentStrip,SuccessDial,UnitMeter,DurationRange,DurationStrip}.tsx;
apps/web/src/app/components/entity/gauges/vega/{common,instrumentSpecs,chartSpecs}.ts and {OverviewChart,charts}.tsx;
apps/web/src/app/dashboard/overviewFilter.ts;
apps/web/src/app/components/entity/Encodings.tsx (StatusLegend, StatusBreakdown);
apps/web/src/app/dashboard/{ExecutionOverview,DashboardPage,dashboardWidgets}.tsx; apps/web/src/app/renderers/ProjectViewer.tsx;
apps/web/src/components/settings/SettingsShell.tsx; apps/web/src/app/settings/AppearancePanel.tsx;
apps/web/src/lib/{ui-theme,ui-scale}.ts; apps/web/src/app/layout/ContextBar.tsx;
apps/web/src/components/layout/PageHeader.tsx; apps/web/src/components/workbench/WorkbenchStatusStrip.tsx;
../molcrafts-ui/packages/ui/src/components/ui/{button,input,badge}.tsx;
../molcrafts-ui/packages/vega/src/charts.tsx.
Sidecar tonal ramps are synthesized preview metadata, not application palette additions.
Evidence: .impeccable/review/*.png are authorized local seeded examples, not live Arrhenius verification.
Production build acceptance remains outside this visual record: preexisting external molvis/molrs interface mismatch.
-->
