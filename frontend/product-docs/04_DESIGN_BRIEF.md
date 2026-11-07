# 04 — Design Brief

## 1. Direction

Build a **dark, dense quantitative research workstation** with the usability of a modern SaaS product. Use Alpha Harness as the strongest design-system reference and the user-supplied Brain screenshots as functional references for alpha lists, simulation settings, performance charts, IS/OS summaries and validation sections.

Do not reproduce another product's branding or pixel-perfect assets. Recreate the functional ideas in a coherent Unified Backtester visual system.

## 2. Design principles
1. Data density over decoration.
2. A single accent for execution, selection and focus.
3. Color is semantic: positive/negative results, job status and taxonomy.
4. Numbers align and compare easily.
5. Controls are compact but legible.
6. Split panes and table columns adapt to research tasks.
7. Every result must show its context and limitations.
8. Consistent state feedback beats animation.

## 3. Visual tokens (recommendation)

The exact tokens should be implemented in one source-of-truth file. Alpha Harness's `DESIGN.md` uses a near-black canvas, a ladder of dark surfaces, hairline dividers, a restrained lavender accent, Inter-like text, JetBrains Mono for code/figures, and semantic positive/negative/status colors. Adopt the *principles*, then define our own approved tokens.

Suggested palette roles:
- Canvas: near-black.
- Surface 1–4: subtly stepped dark grays.
- Primary accent: restrained lavender/blue-violet for Run, focus and selected states.
- Text: high-contrast primary, muted secondary, subtle labels.
- Positive: green; negative: red; warning: amber.
- Job states: idle, queued, running, warning/blocked.
- Operator categories: distinct low-saturation category hues; taxonomy color must not imply performance.

Do not hardcode arbitrary colors inside components. Use semantic tokens. Positive/negative number color is derived from value sign, not selected manually.

## 4. Typography and density
- Sans-serif UI font for labels/body; monospace font for expression, IDs and numerical metrics.
- Tabular numerals for aligned metric values.
- Compact scale with a small set of sizes; reserve large display text for a limited workspace empty-state/summary use.
- Dense table rows with clear column hierarchy and enough spacing for scanning.
- Avoid oversized hero cards, large rounded pills, gradients and decorative shadows.

## 5. Layout
- Full-width, viewport-oriented workspace; do not center all content in a narrow marketing container.
- Left nav + top bar + main workspace.
- Editor and configuration/field browser use a draggable split pane.
- Result page uses a responsive grid of metric panels and chart panels.
- Table pages use server-side sorting/filtering/pagination and a column chooser.
- At narrower desktop widths, stack side panes or allow collapse; mobile is not a launch priority but the layout should not become unusable.

## 6. Key components
- `AppShell`, `SideNav`, `TopBar`, `WorkspaceHeader`
- `Panel`, `PanelHeader`, `Metric`, `MetricBadge`, `StatusBadge`, `Notice`
- `DataTable`, `ColumnChooser`, `FilterRow`, `Pager`
- `SplitPane`, `ResizeHandle`
- `ExpressionEditor`, `InlineExpressionError`, `OperatorBrowser`, `FieldBrowser`, `TemplatePicker`
- `ConfigurationPanel`, `SettingGroup`, `UniversePicker`, `DateRangeControl`
- `RunStatus`, `RunQueue/RunDrawer`, `ProgressStageList`
- `PerformanceChart`, `ChartMetricSelector`, `TimeRangeControl`
- `ValidationAccordion`, `ValidationStatusCounts`
- `RunComparisonTable`, `ExportMenu`, `ConfirmDialog`, `Toast`

Keep shared primitives in a UI folder and domain components separate from generic primitives.

## 7. Brain-inspired screen details

### Alpha table
Use a compact header and rows. Include sortable column headings, per-column filter controls, column selection and visible status. Support high row counts without rendering every row at once.

### Alpha detail
Show expression prominently in a code-style panel. Place simulation settings beside/under it in a horizontally scrollable or grouped layout. Offer clone/open actions. Keep saved configuration tied to the result.

### Performance chart
Allow selection of the plotted metric/series (e.g. cumulative PnL/returns), legend toggles, date range/zoom and tooltips. The chart must label units and date coverage. Never plot missing data as zero without explicit semantics.

### IS/OS and yearly summary
Use clear period selectors and a compact yearly table. In MVP, map this to the engine's train/validation/test and walk-forward concepts; do not label a period “out-of-sample” unless the methodology actually matches.

### Validation
Expandable sections grouped into pass/fail/warning/pending/skipped. Show last run time and evidence. A failed check must have an explanation and should not be hidden behind a collapsed summary by default if it blocks acceptance.

### Editor
Use syntax highlighting based on engine registry metadata: operator names, field names, constants and punctuation. Do not hardcode syntax rules separately from the engine interface manifest.

## 8. Motion and feedback
- Short transitions only for state changes.
- Avoid decorative motion.
- Run button state changes immediately to queued only after the API confirms durable queueing.
- Show loading skeletons, not jumping layouts.
- Use toasts for non-blocking confirmations; inline notices for validation and run failures.
- Respect reduced motion.

## 9. Accessibility
- Focus ring on all interactive elements.
- Accessible labels on icon-only buttons.
- Keyboard operation for menus, tables, split panes and editor helpers.
- Text/sign/icon accompanies semantic color.
- Check contrast for text and important metrics; test charts with color-vision simulations.
- Do not rely on hover-only information.

## 10. Design references
- Alpha Harness repository: https://github.com/residual-lab/alpha-harness
- Alpha Harness design system: https://github.com/residual-lab/alpha-harness/blob/main/DESIGN.md
- Brain UI screenshots: user-provided `UI elements.pdf` (alpha table, detail/settings, performance chart, IS summary, validation panel, editor/result split)
