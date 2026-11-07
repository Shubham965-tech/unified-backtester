# 03 — Application Flow and Interaction Specification

## 1. Global shell

### Recommended layout
- Persistent left navigation: Alpha Workspace, Create Alpha, Saved Alphas, Runs/History, Screeners, Investment (deferred).
- Top bar: workspace selector, search, run/core status summary, account menu.
- Main canvas: dense full-width research workspace; avoid excessive whitespace.
- Global run status can be opened to inspect queued/running jobs.

The shell should feel like a quant workstation: direct, compact and persistent. Do not make a marketing landing page the default authenticated experience.

## 2. First-use flow

1. User opens app → public sign-in/sign-up route.
2. Managed auth completes → backend verifies token and provisions user/workspace if needed.
3. Redirect to Alpha Workspace.
4. Empty state offers “Create alpha”, a starter template and a short explanation of the expression → configuration → run → inspect cycle.
5. User creates alpha → opens editor/configuration page.

Unknown: exact managed-auth provider and onboarding fields.

## 3. Alpha Workspace / saved-alpha list

Inspired by Alpha Harness's research-workstation density and the supplied Brain alpha list.

### Table behavior
- Server-side pagination, sorting and filtering.
- Column chooser.
- Search by name, expression and tags.
- Useful columns: name, status, latest run, universe, date range, Sharpe, net return, turnover, IC, created/updated time, tags.
- Distinguish alpha draft status from latest run status.
- Row actions: open, clone, run, rename, archive/delete (confirm destructive actions), add/remove tags.
- Filters should not pretend unavailable metrics exist; metrics are blank until a completed run exists.

### States
- First-use empty
- No filter results
- Loading skeleton
- API error with retry
- Stale latest-run indicator
- Alpha with no runs
- Alpha with running job
- Alpha with failed last run

## 4. Create / edit alpha

### Layout
Resizable split workspace:
- **Left/main pane:** monospaced expression editor, line numbers, inline parse/field/operator errors.
- **Side pane:** settings and operator/field browser, resizable/collapsible.
- Optional bottom/side validation area with expression parse state and preflight feedback.

### Editor interactions
- Plain text expression is the source of truth.
- Operator/field browser can search, categorize and insert at cursor.
- Categories should mirror the engine registry, not a hardcoded taxonomy.
- Hover/help shows signature, arguments, short description and examples where engine metadata supports it.
- Templates insert valid starter expressions.
- Save/autosave has visible state and version history.
- Invalid expression blocks queueing but does not discard edits.
- Never silently rewrite an expression into a different expression.

### Configuration panel
Group controls:
1. **Universe** — preset selector; future custom/Screener-generated universe option appears only when adapter/engine contract supports it.
2. **Date range** — start/end and available-data hints.
3. **Portfolio construction** — portfolio type, weighting, long/short exposure, max position weight, buckets and `k`.
4. **Execution** — holding period, execution price, execution lag, transaction cost, slippage.
5. **Advanced / diagnostics** — validation options, optional group mapping, future data-source selectors.

Show engine defaults and indicate which settings were explicitly changed. Validate field types/ranges before enqueue.

## 5. Run submission and monitoring

1. User presses **Run backtest**.
2. Frontend sends expression version and complete config.
3. API returns run ID and queued state after durable snapshot/job creation.
4. UI navigates to run detail or opens a run drawer; user can continue working elsewhere.
5. Status updates via polling initially; server-sent events/websocket can be added if justified.
6. Status includes queued/running stage, elapsed time, start time and cancellation action if supported.
7. Cancel requires confirmation if job has already started; cancellation is best-effort.
8. A run failure remains in history and links to a safe error explanation.

Do not show a fabricated percentage progress bar unless the worker emits meaningful stage progress.

## 6. Run detail / result inspection

### Header
- Alpha name, run ID, status, created time, engine version.
- Expression snapshot and configuration summary.
- Actions: clone alpha from this version, rerun with modified config, export, compare, open history.

### Primary metric strip
Use only metrics actually supplied by the engine and normalize their units:
- Sharpe (gross/net if available)
- Annualized/net return
- Max drawdown
- Turnover
- IC mean
- Coverage/data-quality warnings
- Optional Sortino, Calmar, win rate, benchmark-relative stats where available

Metric names, annualization and unit conventions must be validated against the engine result schema before frontend implementation.

### Charts
Use selectable chart tabs or dropdown:
- Cumulative gross vs net return
- Drawdown
- Rolling Sharpe
- Rolling IC / IC distribution
- Turnover
- Quantile/bucket performance
- Exposure over time
- Benchmark comparison if supported

Interactions: hover tooltips, zoom/range selection, legend toggles, visible units, empty/missing-series handling. Keep data colors semantic and consistent.

### Tables / expandable panels
- Year-by-year metrics
- Data quality and coverage
- Universe metadata / survivorship warning
- Validation checks grouped by status: pass, fail, warning, pending, skipped/error
- Walk-forward windows
- Sensitivity by year, holding period, costs and portfolio construction
- Parameter sensitivity
- Correlation/redundancy report

Validation panels should be expandable and report the check definition, result, message, and evidence. A green/red summary is not enough by itself.

## 7. Run comparison

- Select two or more completed runs.
- Show a metric comparison table with same units and clear missing values.
- Display differences in expression, universe, date range, holding period, execution, costs, weighting and engine/data versions.
- Optional aligned cumulative-return charts.
- Warn if comparison is not apples-to-apples.
- Do not rank/select a winner automatically based only on one metric.

## 8. History and versioning

- Alpha versions are immutable snapshots of expression and editable configuration.
- Runs always point to one alpha version plus a frozen run config.
- History timeline shows save/version events and run attempts.
- Autosave indicates saved/saving/error; failed autosave preserves local draft until retried.
- A run can be cloned into a new editable alpha/version, but not modified in place.
- Deleted/archived alpha policy must not silently delete audit/history rows; exact retention policy remains open.

## 9. Screener navigation

- Unified navigation includes Screeners.
- First implementation may link to the existing standalone Screener app.
- If same-origin/SSO or API-level integration is required, decide only after inspecting both repositories.
- Screener-generated universe selection is not considered supported until the API can pass a stable universe snapshot into the Python engine. Current notebook API takes a named preset string.

## 10. Export behavior

- CSV: tabular series/metrics with documented columns and units.
- JSON: immutable config snapshot, engine/data metadata, summary metrics, validation summary and artifact references; optionally include compact series only within size limits.
- Large outputs should be exported from object storage via short-lived authorized links.
- Export generation must use stored results, not rerun the experiment.

## 11. Global states and accessibility
- Loading, empty, stale, warning, partial success, failed, cancelled and permission-denied states.
- Keyboard-accessible editor, operator browser, tables and dialogs.
- Visible focus ring; icon-only actions have accessible labels.
- Color never carries meaning alone; include text/sign/icons.
- Reduced-motion preference supported.
