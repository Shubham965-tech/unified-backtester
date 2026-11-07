# Unified Backtester — Responsive React UI

A desktop-first but responsive quantitative research workstation based on the supplied PRD, Technical Requirements, App Flow, and Design Brief.

## Included
- Alpha-first app shell: Alpha Workspace, Create Alpha, Saved Alphas, Runs & History, Screeners placeholder, Investment deferred.
- Dense dark surfaces with a restrained lavender accent, semantic green/red/amber statuses, Inter UI text and DM Mono for expressions/numbers.
- Alpha table with search, status filtering, sorting, column chooser, templates, and row-to-editor flow.
- Expression editor, engine manifest-driven fields/operators when `/api/meta` is available, settings, preflight state, and backtest submission.
- Results view with cumulative net/gross returns, drawdown, rolling Sharpe, IC, turnover, exposure, quantile and yearly panels, validation evidence, and universe warnings.
- JSON and CSV exports; cURL copy helper.
- Responsive sidebar drawer, stacked settings and single-column charts on smaller viewports.
- Synthetic preview data is clearly labelled and shown if the API is offline.

## Run locally
Requires Node.js 18+.

```bash
npm install
npm run dev
```

Open http://localhost:5173.

## Flask API connection
The Vite dev server proxies `/api/*` to `http://localhost:3000` by default.

Start the existing Flask API in another terminal:

```bash
cd backend
python app.py
```

If your Flask server is on a different host/port:

```bash
VITE_PROXY_TARGET=http://localhost:3000 npm run dev
```

For a separately hosted API, set `VITE_API_URL` in a `.env` file at build time, for example `VITE_API_URL=https://api.example.com`.

## API contract used
This UI currently uses the existing Flask routes:
- `GET /api/health`
- `GET /api/meta`
- `GET /api/examples`
- `GET /api/experiments`
- `POST /api/backtest`

The supplied architecture documents propose a future Node.js API under `/api/v1`. Those routes are intentionally not assumed to exist yet. Authentication, Postgres persistence, background queueing, per-user isolation, durable immutable snapshots, and production export endpoints require the Node/API implementation described in the documents; this browser UI does not fake those backend guarantees.

## Notes
- A successful API response replaces the demo result. If a request fails, the UI shows a toast and illustrative preview results.
- The validation panel uses descriptive preview checks. Only render real validation results once the API exposes their actual statuses and evidence.
- `Screeners` is intentionally a placeholder until its repository/API integration is audited. `Investment` is deferred.
- Run comparisons are a UI preview, not an automatic strategy ranking.
- Before production, add managed authentication, authorization, server-side persistence, run polling/cancellation, durable artifacts, tests, and API versioning.
