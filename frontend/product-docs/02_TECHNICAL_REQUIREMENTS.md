# 02 — Technical Requirements and Architecture

## 1. Architecture decisions

### Confirmed
- Frontend: React.
- Application API/backend: Node.js.
- Research engine: separate Python service/worker boundary.
- Database: Postgres.
- Auth: managed provider.
- Background jobs: required; exact queue technology is a recommendation to choose.
- Artifacts: object storage recommended.
- Cloud hosting, staging, CI and isolation gates required.
- New application organization; do not tightly couple it to the existing Screeners deployment.

### Recommended high-level topology

```text
Browser (React)
  ├── Alpha workspace / expression editor / charts / tables
  └── Managed-auth session
          │ HTTPS + user token
          ▼
Node.js API
  ├── AuthN/AuthZ + ownership checks
  ├── Alpha draft/version service
  ├── Run configuration validation
  ├── Run/job lifecycle and status API
  ├── Screener adapter (after audit)
  └── Postgres
          │ create immutable run snapshot + enqueue job
          ▼
Job queue ──────────────── Worker scheduler / concurrency limits
                              │
                              ▼
                     Python engine worker
                     ├── Load pinned engine release
                     ├── Resolve data/universe
                     ├── Evaluate expression
                     ├── Run backtest
                     ├── Run validation/robustness tasks
                     ├── Serialize results and diagnostics
                     └── Write artifacts
                              │
                    Postgres result metadata + object storage
                              │
                              ▼
                    Node API → React result view
```

## 2. Separation of responsibilities

### React frontend
- Own page layout, editor interactions, local unsaved state, chart/table presentation and progress polling.
- Request operator/field/config manifests from the API.
- Submit alpha edits and run requests; do not execute Python or market-data retrieval in the browser.
- Display server-side validation results and preserve run IDs in URLs.
- Never treat a disabled UI control as a security boundary.

### Node.js API
- Authenticate every request and enforce resource ownership.
- Validate shape, size, supported enum values and user limits before enqueueing.
- Persist alpha drafts/versions and immutable run configuration snapshots.
- Create job records transactionally with run snapshots.
- Enqueue work using an outbox or equivalent reliable handoff to avoid “database row saved but job not queued”.
- Expose status, result metadata, comparison and export endpoints.
- Store only summary/structured metadata in Postgres; store large series/plots/reports in object storage.
- Map internal exceptions to stable safe error envelopes; never expose tracebacks or secrets.
- Keep the Screeners integration behind an adapter until the old repositories are audited.

### Python worker
- Treat the notebook as the research source of truth initially, but do not run a notebook UI session as a web request.
- Refactor the notebook's reusable logic into an importable, versioned Python package/module; retain the notebook as a research/debugging artifact and regression notebook.
- Expose a worker callable wrapping `run_backtest_api()` or a stable successor.
- Execute each job in a bounded, isolated worker process/environment with explicit dependency versions, timeout and resource limits.
- Do not depend on global in-memory `TRACKER` for production persistence.
- Return structured JSON-safe metadata and write time-series/large artifacts separately.
- Run main backtest first; validation/robustness stages can be separate child tasks so the core result can be available even if an optional analysis fails.

## 3. Existing notebook: observed interface and limits

### Observed in supplied notebook
- Main entry point: `run_backtest(expression, universe, start, end, ...)`.
- Website handoff callable: `run_backtest_api(request, ...)`.
- Request validation rejects unknown fields, validates types/ranges and normalizes dates/numeric fields.
- Result envelope is shaped as:
  `experiment_id`, `status` (`success`/`error`), `error`, `config`, `result`.
- Result serialization is intended to be JSON-safe.
- Universe allowlist in this distribution: `NIFTY50` only. The backend rejects all other values.
- Engine features include OHLCV data foundation, universe construction, external-score import, feature engineering, AST expression interpreter/operator library, execution timing, portfolio construction, transaction costs/slippage, IC/risk/quantile/benchmark/exposure/data-quality diagnostics, leakage tests, train/validation/test, walk-forward, sensitivity analysis, alpha correlation, and synthetic regression tests.
- `ExperimentTracker` has in-memory records plus explicit JSON file save/load. This is not multi-user durable storage.

### Explicitly absent from notebook
- HTTP server/routes
- Managed authentication or user authorization
- Background queue and job scheduler
- Distributed concurrency control
- Postgres persistence or multi-user isolation
- Object storage
- Cloud deployment/monitoring/secret management
- Point-in-time guarantees for every alternative/fundamental dataset

### Required engine audit before API freeze
1. Run all deterministic/synthetic tests in a fresh kernel and record pass/fail.
2. Inspect `describe_interface()` and generated expression/operator manifest.
3. Confirm full result object serialization with representative data and non-finite values.
4. Confirm exact supported enum values and defaults from runtime, not copied docs.
5. Verify if `group_map` can be safely transported at scale; if not, pass a stored mapping artifact/reference.
6. Audit the universe loader, fallback definitions, cache paths, data provider rate limits and stale-cache behavior.
7. Measure runtime and memory for representative universes/date windows.
8. Confirm how validation functions receive already-loaded data and whether repeated calls refetch/recompute.
9. Establish data limitations and label point-in-time/survivorship risks in results.
10. Produce `ENGINE_AUDIT.md`, `engine-contract.json` and a clean-kernel test report.

## 4. Pipeline integration contract

The production path should be implemented as a staged job orchestrator. The notebook's `run_backtest_api()` is the initial engine adapter, not the queue or HTTP API.

### Request-to-result pipeline
1. **Draft saved** — React sends expression and configuration to Node; Node stores a versioned alpha draft.
2. **Preflight validation** — Node checks required fields, field types, allowed enum values and user quotas. Python expression validation checks syntax, operators and fields. The UI renders returned errors inline.
3. **Immutable snapshot** — Node creates a run row with `alpha_version_id`, normalized config JSON, engine release/version and data/universe request metadata. This snapshot cannot be edited.
4. **Job enqueue** — Node writes the job and an outbox event in one transaction. Queue dispatcher publishes the job. Duplicate delivery must be safe/idempotent.
5. **Worker claim** — worker claims job, checks ownership/quota, records start time and emits progress/status.
6. **Engine initialization** — worker loads a pinned engine package, verifies dependency manifest, initializes data cache/provider and resolves the selected universe.
7. **Data foundation** — load OHLCV and any selected external/fundamental/technical fields; record date range, field coverage, source and cache/data version. Do not claim point-in-time correctness unless verified.
8. **Universe construction** — resolve preset or stored Screener-generated ticker set; persist a snapshot/hash and metadata. The current notebook's API only accepts named preset strings, so explicit custom universe support requires a deliberate engine adapter/contract change.
9. **Feature and expression stage** — compute required features, validate AST, resolve operators/fields, evaluate expression and align signal to configured execution timing.
10. **Backtest stage** — build portfolios, apply holding period, weighting, execution price/lag, transaction costs and slippage; produce the core `BacktestResult`.
11. **Core result commit** — serialize and validate result, persist summary/metrics in Postgres, store large series/artifacts in object storage, set run status `succeeded` (or `failed` with safe error).
12. **Validation child stages** — execute train/validation/test, walk-forward, leakage checks, data quality, sensitivity/robustness, parameter sweeps and correlation as configured. These should not silently mutate the core result or choose a “best” run. Persist each check with pass/fail/warning/pending/error.
13. **Completion** — aggregate status, publish status event, expose chart series and diagnostics to the result UI.
14. **Export** — generate CSV/JSON from the stored immutable result, not by rerunning the engine.

### Progress states
Use a stable lifecycle: `queued → running → succeeded | failed | cancelled`; use separate child-stage/check states such as `pending`, `running`, `passed`, `failed`, `warning`, `skipped`. Do not use one ambiguous status for both job execution and scientific validation.

### Idempotency and failure rules
- Each run has one immutable `run_id`; the engine's `experiment_id` is an internal correlation ID unless adopted as the canonical run ID.
- A worker retry must not create duplicate runs or overwrite a successful result with a partial result.
- Failed runs keep the input snapshot, structured error and logs reference.
- Cancel requests are best-effort; worker checks cancellation at safe boundaries.
- If core backtest succeeds but a validation child fails, keep core results available and show validation failure separately.
- Large arrays/series are written atomically to versioned artifact paths; mark result ready only after metadata and artifacts are consistent.
- Retry transient provider/infra failures only; don't retry deterministic invalid expressions endlessly.

## 5. API design (proposed, not existing contracts)

Prefix all endpoints with `/api/v1`. Exact routes can be finalized after implementation conventions are chosen.

- `GET /api/v1/engine/interface` — engine version, supported fields/operators/enums/config defaults.
- `GET /api/v1/alphas` / `POST /api/v1/alphas`
- `GET /api/v1/alphas/:id` / `PATCH /api/v1/alphas/:id`
- `GET /api/v1/alphas/:id/versions`
- `POST /api/v1/alphas/:id/runs` — validate snapshot, create run, enqueue.
- `GET /api/v1/runs/:id` — state, config snapshot, summary.
- `POST /api/v1/runs/:id/cancel`
- `GET /api/v1/runs/:id/results`
- `GET /api/v1/runs/:id/validation`
- `GET /api/v1/runs/:id/artifacts/:artifactKey`
- `POST /api/v1/runs/compare`
- `GET /api/v1/runs/:id/export?format=csv|json`
- `GET /api/v1/workspaces/:id/screeners` only if an adapter/real endpoint is established.

All IDs are authorization-scoped. These paths are suggestions; do not implement against them before the API contract is approved.

## 6. Queue, deployment and observability recommendations

- Choose a managed or well-supported queue compatible with the deployment environment; do not couple the UI to queue vendor.
- Use worker concurrency caps and per-user quotas; Python processes can be memory-heavy.
- Store secrets in the deployment provider's secret manager.
- Separate staging and production databases/buckets/queues.
- Include run ID, job ID, user ID, engine version and data version in structured logs.
- Metrics: queue wait time, run duration by universe/date span, success/failure rate, memory/CPU, provider error rate, cache hit rate, artifact-write failures.
- CI: lint/type checks, unit tests, API tests, engine synthetic suite, migration checks, worker integration tests, frontend tests and deployment smoke test.
- Feature branches and PR review; separate agents/owners for frontend, API/schema, Python engine and QA/integration.

## 7. Security and reliability
- Verify auth token server-side and authorize resource ownership in every query/mutation.
- Do not trust `user_id` sent in a body; derive identity from verified session.
- Validate expression length, config ranges, ticker-list sizes, dates and artifact keys.
- AST interpreter allowlist only; no arbitrary Python evaluation, imports, filesystem or network access from expression strings.
- Use parameterized SQL, rate limits, request limits and secure CORS.
- Keep per-user storage keys or enforce ownership on every signed artifact URL.
- Avoid logging raw secrets or sensitive environment variables.
- Apply migrations and backups; define retention and deletion policy before public launch.
