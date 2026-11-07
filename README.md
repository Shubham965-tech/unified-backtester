# Unified Backtester — connected frontend + backend

This package keeps the previously created React frontend design and connects it to a separate Python Flask API wrapping the uploaded `alpha_backtesting_engine_production_hardened` notebook.

## Project structure

- `frontend/` — existing React + Vite + Recharts UI and CSS; no Tailwind.
- `backend/app.py` — HTTP API, validation boundary, result adapter for the frontend, and local experiment-log persistence.
- `backend/alpha_engine.py` — implementation cells exported from the notebook, including the original expression engine, feature/operator registry, backtest runner, `BacktestResult`, `describe_interface()` and `run_backtest_api()`.
- `backend/storage/experiment_log.json` — created after the first API run to persist the notebook tracker locally.
- `backend/data_cache/`, `backend/universes/`, `backend/external_scores/` — paths expected by the notebook engine.

## Start the backend

Python 3.10+ recommended.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
pip install -r requirements.txt
python app.py
```

The API listens at `http://127.0.0.1:3000`.

The engine uses live Yahoo Finance data through `yfinance` by default. Install `pyarrow` (included in requirements) for the notebook's parquet cache. This distribution is restricted to NIFTY50; its constituent list is loaded from `backend/universes/nifty50.csv` when supplied, otherwise the bundled fallback list is used.

## Start the frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite forwards `/api/*` to the Flask API on port 3000. The existing UI components and CSS are retained; the API adapter converts the notebook result's time-series dictionaries into the chart-friendly format used by the frontend.

## API routes

- `GET /api/health` — backend and engine availability.
- `GET /api/meta` — live engine interface contract (fields, operators, universes, portfolio/weighting options).
- `GET /api/examples` — starter alpha expressions.
- `GET /api/experiments` — notebook experiment tracker history.
- `POST /api/backtest` — validates the JSON request using the notebook's `run_backtest_api()`, executes the engine, adapts the actual result for the UI and persists the tracker snapshot.

Example request:

```bash
curl -X POST http://127.0.0.1:3000/api/backtest \\
  -H 'Content-Type: application/json' \\
  -d '{
    "expression": "rank(ts_zscore(momentum_20, 20))",
    "universe": "NIFTY50",
    "start": "2022-01-01",
    "end": "2025-12-31",
    "holding_period": 5,
    "portfolio": "LONG_SHORT",
    "weighting": "EQUAL_WEIGHT",
    "transaction_cost_bps": 10,
    "slippage_bps": 5,
    "execution_lag_bars": 1,
    "execution_price": "close"
  }'
```

