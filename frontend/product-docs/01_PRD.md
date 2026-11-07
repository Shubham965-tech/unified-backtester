# 01 — Product Requirements Document

## 1. Product definition

Unified Backtester is a public, cloud-hosted quantitative research SaaS inspired by the research workflow and dense information presentation of WorldQuant BRAIN, with Alpha Harness as a strong reference for the day-to-day workstation experience. The platform is organized around **Screeners / Alpha / Investment**. The first release prioritizes **Alpha**; Screeners remain usable as a standalone application; Investment is deferred.

The core promise: let a researcher define an alpha expression, configure an experiment, run the research pipeline, inspect performance and validation evidence, compare experiments, and save reproducible results.

## 2. Target users and usage assumptions

### Confirmed
- Public SaaS from the beginning.
- Individual accounts and saved workspaces.
- Desktop-first initially.
- Single-user research workflows first; no collaboration in MVP.
- Dense, dark, hybrid quant-workstation/SaaS UI.
- React + Node backend; Python research engine is a separate service/worker.
- Postgres is the system-of-record database; managed authentication.
- Cloud deployment; durable saved runs and outputs.
- Alpha-first release; Investment comes later.
- The existing repositories are reference implementations to inspect, not mandatory hard dependencies.

### Product principles
1. **Research-first, not marketing-first:** put expression, settings, run state and evidence near each other.
2. **Reproducibility:** each run is an immutable snapshot of the exact expression, parameters, engine version and available data metadata.
3. **No silent errors:** invalid expressions/configuration fail visibly with field-level feedback.
4. **Trustworthy validation:** show test status and limitations, not only headline Sharpe/returns.
5. **Fast navigation:** move between editor, run queue, results, saved alphas and history without losing work.

## 3. MVP workflow

The MVP must support the complete lifecycle:
1. Sign in.
2. Open Alpha workspace.
3. Create a new alpha or open an existing one.
4. Enter/edit an expression directly.
5. Use operator browser, field browser and starter templates.
6. Configure universe and full backtest settings.
7. Validate expression/config before queueing.
8. Submit an asynchronous run.
9. See queued/running/success/warning/error status and navigate away safely.
10. Open a result detail page with metrics, charts, tables and validation.
11. Save alpha and immutable run snapshots.
12. Browse experiment history, compare runs, and export CSV/JSON.

## 4. Navigation / product areas

### Confirmed
- Top-level information architecture: Screeners / Alpha / Investment.
- Alpha is the primary landing area for launch.
- Unified navigation should coexist with a separately deployable Screeners app.
- Research history belongs in the workspace.
- Alpha creation and editing are separate flows.
- Editor layout is resizable.
- Operator/field browser inserts into the expression.
- Results use charts and a comparison table.
- Dark theme; dense hybrid style.

### Proposed navigation
- **Alpha Workspace**: saved alpha list, recent runs, status, search/filter.
- **Create Alpha**: editor + configuration + validation.
- **Alpha Detail / Run Detail**: expression, frozen run settings, metrics, chart panels, validation.
- **Compare Runs**: select immutable runs and compare metrics.
- **Screeners**: route/link to the existing Screener application; integration depth decided after repository audit.
- **Investment**: visible as “Coming later” or omitted from primary action until approved; do not implement portfolio optimizer in this release.

## 5. Alpha entity and run semantics

### Confirmed
- The main research object is an **alpha expression**.
- A run uses a complete configuration, not just expression text.
- Parameters are configurable.
- Runs are immutable.
- Autosave and versioning are both required.
- Full configuration, metrics, reports and history are saved.
- CSV and JSON exports are required.
- Private research by default; no collaboration in first release.

### Required behavior
- Editing an alpha does not rewrite prior runs.
- Queueing a run creates an immutable run snapshot.
- Autosave updates the editable alpha draft/version; the queued run references a frozen snapshot.
- Run status and failure are persisted, not only shown in browser memory.
- A result must record the engine version, configuration, timestamps, data/universe metadata where available, and validation state.
- Comparing runs must compare snapshots, and clearly flag differences in settings.

## 6. Research configuration

### Engine-backed controls currently documented in the supplied notebook
- Expression
- Universe: `NIFTY50` only in this distribution; the selector is fixed and other universes are disabled
- Start and end dates
- Portfolio type and weighting scheme
- Holding period
- Transaction cost and slippage in basis points
- Execution lag and execution price (`open`/`close`)
- Quantile bucket count, `k`, maximum position weight
- Long and short exposure
- Optional group mapping in the in-process contract

The notebook's `describe_interface()`/operator registry is the source of truth for accepted enum values and expression fields. The web UI must consume a generated/versioned interface manifest or a backend endpoint, rather than maintaining a hand-written list that can drift.

### Future extensibility
The platform should be modular for future sources/signals, including sentiment, IPO-related predictions, analyst signals and chart-derived scores. They are not automatically available just because the UI is extensible: each source needs a documented schema, availability timestamp, coverage rules, and leakage tests before it is allowed in research.

## 7. Validation and result inspection

### Confirmed
- Validation is integrated into the normal workflow.
- The validation suite should be recommended by the implementation team and is not fully user-specified.
- Result detail should include charts.
- Run comparisons use a table.
- Full metrics and reports should be available.
- Failures should be handled with structured feedback.
- Chart/table interactions should be recommended as part of the implementation.

### Recommended initial validation panels
- Chronological train / validation / test split
- Walk-forward results
- Leakage diagnostics
- IC and return/risk diagnostics
- Turnover, costs and slippage sensitivity
- Parameter/universe/holding-period sensitivity
- Alpha signal/return correlation and redundancy
- Data quality and universe coverage
- Warnings for survivorship-bias risk, missing data, low coverage, and multiple testing

These capabilities exist in some form in the supplied notebook, but exact execution cost, run time and UI representation must be verified with synthetic and representative live-data tests. Sensitivity results must be presented as evidence, not as an optimizer that automatically selects a winner.

## 8. Reference-inspired functionality

### Alpha Harness inspiration
- Workstation-style dashboard rather than a conventional landing-page-heavy SaaS.
- Dense metric grids and server-sortable/filterable tables.
- Explicit simulation/run status.
- Resizable split panes.
- Monospaced expression editor and numerical metrics.
- Operator taxonomy and insertion helpers.
- Small semantic color vocabulary: accent for action/focus, positive/negative for result sign, separate status colors for queued/running/warning.
- Saved workspace, history and result inspection as primary concepts.

### Brain UI screenshot inspiration
- Alpha list table with column selection, sorting, per-column filters, status/type/region/universe metadata.
- Alpha detail drawer/page with expression, simulation settings and cloning.
- Performance chart with selectable metric and time-range control.
- IS/OS or train/test summary controls and yearly metric table.
- Expandable validation sections with pass/fail/warning/pending counts.
- Performance comparison panel.
- Research settings visible and tied to each result.

Recreate the useful workflow and information architecture, not exact branding or pixel-for-pixel screens.

## 9. Non-functional requirements

- Strict per-user data isolation.
- Managed auth, authorization checks on every saved object and run.
- Background execution with bounded concurrency, timeout and cancellation policy.
- Cloud deployment with staging environment.
- CI checks and unit/integration/e2e testing.
- Structured logs, run-level correlation IDs, metrics and alerting.
- Safe expression interpreter; never use raw Python `eval` for user expressions.
- JSON-safe API payloads and explicit API versioning.
- Secure secrets management; no secrets committed to notebooks or repositories.
- Reproducible dependency/environment manifest.
- Accessible focus states and no color-only communication.

## 10. Acceptance criteria

A release candidate is acceptable when:
- A new user can authenticate and create an alpha.
- The editor validates syntax and unknown operators/fields with inline errors.
- A valid run is stored as a frozen snapshot and submitted to a worker.
- The worker invokes the audited engine interface and emits structured results/errors.
- Browser refresh/navigation does not lose run status or saved outputs.
- A completed run displays key metrics, cumulative gross/net return, drawdown, rolling metrics, IC, turnover, quantile/bucket information, exposure and validation status where supplied by the engine.
- A failed run shows a safe, useful error and remains in history.
- Runs can be compared in a table and exported to CSV/JSON.
- User A cannot read or modify User B's alphas, runs, artifacts or exports.
- CI runs engine synthetic regression tests and web/backend tests.
- The Screeners integration does not break the existing standalone deployment.

## 11. Explicit unknowns / decisions still required
- Exact cloud provider, managed-auth provider, queue technology, object-storage provider and hosting layout.
- Exact Screeners API, database schema, authentication, cron/refresh design and deployment topology; inspect repositories.
- Whether Screener-generated universes can be passed as explicit ticker lists today or need a new engine contract.
- Whether the current data source provides adequate corporate actions, delisted names, point-in-time fundamentals and survivorship-safe universe membership.
- Limits/quotas for run duration, parallel runs, dataset sizes and user storage.
- Exact metric names/units and engine schema version after a clean-kernel integration test.
