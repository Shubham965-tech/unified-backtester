# Exported from alpha_backtesting_engine_production_hardened notebook; core logic preserved.


# --- Exported from notebook cell 3 ---


import os, json, warnings, functools, operator as _pyop, itertools, ast as _ast, importlib.util
from dataclasses import dataclass, field as dc_field
from datetime import datetime

import numpy as np
import pandas as pd
try:
    import yfinance as yf
except ImportError:
    # Allows offline/synthetic regression tests to run in minimal environments.
    # Live data requests fail fast with an actionable dependency message.
    yf = None
from scipy import stats

warnings.filterwarnings("ignore")
pd.set_option("display.width", 160)

CONFIG = {
    "start_date": "2018-01-01",
    "end_date": datetime.today().strftime("%Y-%m-%d"),
    "cache_dir": "./data_cache",
    "universe_dir": "./universes",
    "external_scores_dir": "./external_scores",
    "default_universe": "NIFTY50",

    # --- execution / timing (Section 3) ---
    "execution": {
        "execution_lag_bars": 1,     # bars between signal being known and it being tradeable. 0 = same-bar (optimistic).
        "execution_price": "close",  # 'close' or 'open' — which price series marks entry/exit
    },

    "holding_period": 1,             # bars a position is held before the next rebalance for that cohort
    "quantile_buckets": 5,           # for the LONG_SHORT/QUANTILE portfolio construction default
    "risk_free_annual": 0.0,

    # --- costs (Sections 6-7) ---
    "transaction_cost_bps": 10.0,
    "slippage_bps": 5.0,

    "overfitting_warning_threshold": 20,  # experiments logged before ExperimentTracker warns
}

# This build is intentionally restricted to NIFTY50.
BENCHMARK_TICKERS = {"NIFTY50": "^NSEI"}

os.makedirs(CONFIG["cache_dir"], exist_ok=True)
os.makedirs(CONFIG["universe_dir"], exist_ok=True)
os.makedirs(CONFIG["external_scores_dir"], exist_ok=True)

_DATA_VERSION = 0
def bump_data_version():
    """Call after any data refresh so the expression cache invalidates."""
    global _DATA_VERSION
    _DATA_VERSION += 1
    return _DATA_VERSION

CONFIG


# --- Exported from notebook cell 5 ---


def to_yf_ticker(ticker: str) -> str:
    t = ticker.strip().upper()
    if not t.endswith(".NS") and not t.endswith(".BO") and not t.startswith("^"):
        t = t + ".NS"
    return t


def _cache_path(ticker: str) -> str:
    safe = ticker.replace("/", "_").replace("^", "IDX_")
    return os.path.join(CONFIG["cache_dir"], f"{safe}.parquet")


def fetch_ohlcv_single(ticker: str, start: str, end: str, force_refresh: bool = False) -> pd.DataFrame:
    if yf is None:
        raise RuntimeError("Live OHLCV fetching requires yfinance. Install dependencies from requirements-production.txt.")
    if not (importlib.util.find_spec("pyarrow") or importlib.util.find_spec("fastparquet")):
        raise RuntimeError("OHLCV parquet caching requires pyarrow or fastparquet. Install dependencies from requirements-production.txt.")
    yf_ticker = to_yf_ticker(ticker)
    path = _cache_path(yf_ticker)

    if os.path.exists(path) and not force_refresh:
        cached = pd.read_parquet(path)
        cached.index = pd.to_datetime(cached.index)
        need_start = pd.Timestamp(start)
        need_end = pd.Timestamp(end)
        if cached.index.min() <= need_start and cached.index.max() >= need_end - pd.Timedelta(days=5):
            return cached.loc[start:end]

    raw = yf.download(yf_ticker, start=start, end=end, progress=False, auto_adjust=True)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.rename(columns={"Open": "open", "High": "high", "Low": "low",
                               "Close": "close", "Volume": "volume"})
    raw = raw[["open", "high", "low", "close", "volume"]]
    raw.index.name = "date"
    raw.to_parquet(path)
    return raw.loc[start:end]


def get_ohlcv(tickers, start: str = None, end: str = None, force_refresh: bool = False) -> dict:
    start = start or CONFIG["start_date"]
    end = end or CONFIG["end_date"]

    per_ticker = {}
    for t in tickers:
        try:
            df = fetch_ohlcv_single(t, start, end, force_refresh=force_refresh)
            if not df.empty:
                per_ticker[t] = df
        except Exception as e:
            print(f"[get_ohlcv] failed for {t}: {e}")

    if not per_ticker:
        raise RuntimeError("No data fetched for any ticker in the requested universe.")

    fields = {}
    for col in ["open", "high", "low", "close", "volume"]:
        wide = pd.DataFrame({t: df[col] for t, df in per_ticker.items()}).sort_index()
        fields[col] = wide
    if force_refresh:
        bump_data_version()
    return fields


def fetch_benchmark(universe_name: str, dates: pd.DatetimeIndex) -> pd.Series:
    """Real index level (not a synthetic equal-weight proxy) via the mapped
    ^NSEI / ^CNX100 yfinance ticker, reindexed to the working date grid."""
    ticker = BENCHMARK_TICKERS.get(universe_name.upper())
    if ticker is None:
        return None
    df = fetch_ohlcv_single(ticker, str(dates.min().date()), str(dates.max().date()))
    if df.empty:
        return None
    return df["close"].reindex(dates)


# --- Exported from notebook cell 7 ---


_FALLBACK_NIFTY50 = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "HINDUNILVR", "ITC",
    "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK", "BAJFINANCE",
    "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "NESTLEIND",
    "WIPRO", "ONGC", "NTPC", "POWERGRID", "M&M", "TATAMOTORS", "TATASTEEL",
    "ADANIENT", "ADANIPORTS", "COALINDIA", "BAJAJFINSV", "HCLTECH",
    "INDUSINDBK", "GRASIM", "JSWSTEEL", "TECHM", "DRREDDY", "CIPLA",
    "EICHERMOT", "BRITANNIA", "DIVISLAB", "HEROMOTOCO", "BPCL", "SBILIFE",
    "HDFCLIFE", "APOLLOHOSP", "TATACONSUM", "UPL", "SHREECEM", "BAJAJ-AUTO",
    "HINDALCO",
]


def _load_universe_csv(name: str, required: bool = False, fallback=None) -> list:
    """Loads a universe constituents CSV. If `required` is True, a missing
    file raises FileNotFoundError with an explicit message rather than
    silently substituting a smaller or different universe (Section 6 of the
    hardening pass) — retained as a generic CSV loader. The production build
    currently exposes NIFTY50 only; if `fallback` is given (NIFTY50 only),
    a missing file falls back to a bundled, explicitly-marked-as-not-current
    list, with a printed warning."""
    path = os.path.join(CONFIG["universe_dir"], f"{name.lower()}.csv")
    if os.path.exists(path):
        df = pd.read_csv(path)
        col = "ticker" if "ticker" in df.columns else df.columns[0]
        return sorted(df[col].dropna().astype(str).str.upper().unique().tolist())
    if required:
        raise FileNotFoundError(
            f"{name.upper()} requires a real constituents file at {path} (one 'ticker' column, "
            f"one ticker per row). This universe does NOT fall back to a smaller or different "
            f"universe when the file is missing — that would silently misrepresent what was "
            f"actually backtested. Add the file and retry."
        )
    if fallback is not None:
        print(f"[universe] {path} not found — using bundled fallback list for {name} "
              f"(NOT guaranteed current; drop a real {name.lower()}.csv into {CONFIG['universe_dir']}).")
        return fallback
    raise FileNotFoundError(f"Universe file not found: {path}")


def load_static_universe(name: str = "NIFTY50") -> list:
    """Load the only supported universe: NIFTY50."""
    normalized = str(name).strip().upper()
    if normalized != "NIFTY50":
        raise ValueError(f"Only NIFTY50 is enabled in this build; received {normalized!r}.")
    return _load_universe_csv("nifty50", fallback=_FALLBACK_NIFTY50)


def build_ranked_universe_mask(close: pd.DataFrame, market_cap: pd.DataFrame, top_n: int,
                                rebalance: str = "M") -> pd.DataFrame:
    dates = close.index
    rebal_dates = sorted(pd.Series(dates, index=dates).resample(rebalance).last().dropna().values)
    mask = pd.DataFrame(False, index=dates, columns=close.columns)

    membership = None
    next_rebal_idx = 0
    for d in dates:
        if next_rebal_idx < len(rebal_dates) and d >= rebal_dates[next_rebal_idx]:
            asof = rebal_dates[next_rebal_idx]
            if asof in market_cap.index:
                row = market_cap.loc[asof].dropna()
                membership = set(row.sort_values(ascending=False).head(top_n).index)
            next_rebal_idx += 1
        if membership:
            cols = [c for c in mask.columns if c in membership]
            mask.loc[d, cols] = True
    return mask


def build_static_universe_mask(close: pd.DataFrame, tickers: list) -> pd.DataFrame:
    cols = [c for c in close.columns if c in set(tickers)]
    mask = pd.DataFrame(False, index=close.index, columns=close.columns)
    mask[cols] = close[cols].notna()
    return mask


def get_universe_tickers(name: str = "NIFTY50") -> list:
    normalized = str(name).strip().upper()
    if normalized != "NIFTY50":
        raise ValueError(f"Only NIFTY50 is enabled in this build; received {normalized!r}.")
    return load_static_universe("NIFTY50")


def get_universe(name: str, close: pd.DataFrame, market_cap: pd.DataFrame = None,
                  rebalance: str = "M") -> tuple:
    """Build the static NIFTY50 mask. Other universes are deliberately disabled."""
    normalized = str(name).strip().upper()
    if normalized != "NIFTY50":
        raise ValueError(f"Only NIFTY50 is enabled in this build; received {normalized!r}.")
    mask = build_static_universe_mask(close, load_static_universe("NIFTY50"))
    meta = {
        "name": "NIFTY50",
        "construction_method": "static NIFTY50 constituent list",
        "rebalance_frequency": "N/A (static list)",
        "point_in_time": False,
        "survivorship_bias_risk": True,
        "notes": (
            "The current NIFTY50 constituent list is applied across the full date range. "
            "This is not historical point-in-time membership and carries survivorship-bias risk."
        ),
    }
    return mask, meta


def get_universe_mask(name: str, close: pd.DataFrame, market_cap: pd.DataFrame = None) -> pd.DataFrame:
    """Backward-compatible wrapper around get_universe() -- kept from v1's interface."""
    mask, _ = get_universe(name, close, market_cap)
    return mask


def fetch_shares_outstanding(tickers) -> dict:
    out = {}
    for t in tickers:
        try:
            info = yf.Ticker(to_yf_ticker(t)).fast_info
            shares = getattr(info, "shares", None) or info.get("shares", None)
            if shares:
                out[t] = shares
        except Exception as e:
            print(f"[shares_outstanding] failed for {t}: {e}")
    return out


def build_market_cap_matrix(close: pd.DataFrame, shares_outstanding: dict) -> pd.DataFrame:
    cols = [c for c in close.columns if c in shares_outstanding]
    return close[cols].mul(pd.Series(shares_outstanding)[cols], axis=1)


# --- Exported from notebook cell 9 ---


EXTERNAL_FIELD_METADATA = {}

def load_external_score(csv_path: str, field_name: str, dates: pd.DatetimeIndex,
                         tickers: list) -> tuple:
    """Returns (wide_dataframe, metadata_dict). Validates the CSV schema
    explicitly rather than trusting it silently. Column rules:
      - 'ticker' and 'value' are always required.
      - a date column is required: 'available_date' if present (preferred --
        the date the score becomes tradable/known), else 'date' (treated as
        already being the tradable/known date). If BOTH 'event_date' and
        'available_date' are present, 'available_date' is used for
        alignment -- 'event_date' is informational only and is never used to
        place the score in time."""
    raw = pd.read_csv(csv_path)

    if "ticker" not in raw.columns:
        raise ValueError(f"External score file {csv_path} is missing a required 'ticker' column.")
    if "value" not in raw.columns:
        raise ValueError(f"External score file {csv_path} is missing a required 'value' column.")

    if "available_date" in raw.columns:
        date_col = "available_date"
    elif "date" in raw.columns:
        date_col = "date"
    else:
        raise ValueError(f"External score file {csv_path} must have a 'date' or 'available_date' "
                          f"column (an 'event_date' column alone is not enough -- it doesn't say "
                          f"when the score was actually knowable).")

    if raw["ticker"].isna().any():
        raise ValueError(f"External score file {csv_path} contains empty/missing ticker values.")
    raw["ticker"] = raw["ticker"].astype(str).str.strip().str.upper()
    if (raw["ticker"] == "").any():
        raise ValueError(f"External score file {csv_path} contains empty ticker values.")

    try:
        raw[date_col] = pd.to_datetime(raw[date_col])
    except Exception as e:
        raise ValueError(f"External score file {csv_path}: could not parse '{date_col}' as dates: {e}")
    if raw[date_col].isna().any():
        raise ValueError(f"External score file {csv_path}: some '{date_col}' values failed to parse.")

    if not pd.api.types.is_numeric_dtype(raw["value"]):
        coerced = pd.to_numeric(raw["value"], errors="coerce")
        if coerced.isna().all():
            raise ValueError(f"External score file {csv_path}: 'value' column is not numeric.")
        n_bad = coerced.isna().sum() - raw["value"].isna().sum()
        if n_bad > 0:
            print(f"[external_scores] {csv_path}: {n_bad} 'value' entries were non-numeric and became NaN.")
        raw["value"] = coerced

    n_dupes = int(raw.duplicated(subset=["ticker", date_col]).sum())
    if n_dupes:
        print(f"[external_scores] {csv_path}: {n_dupes} duplicate ticker/{date_col} rows found -- "
              f"keeping the last occurrence (deterministic).")

    wide = raw.pivot_table(index=date_col, columns="ticker", values="value", aggfunc="last")
    wide = wide.reindex(index=dates, columns=tickers)

    meta = {
        "source_file": os.path.basename(csv_path),
        "availability_column": date_col,
        "used_event_date_for_alignment": False,  # always False by construction -- see docstring
        "date_range": (str(raw[date_col].min().date()), str(raw[date_col].max().date())) if len(raw) else None,
        "n_rows": int(len(raw)), "n_duplicate_rows": n_dupes,
    }
    return wide, meta


def register_external_scores(fields: dict, dates: pd.DatetimeIndex, tickers: list,
                              scores_dir: str = None) -> dict:
    scores_dir = scores_dir or CONFIG["external_scores_dir"]
    if not os.path.isdir(scores_dir):
        return fields
    for fname in os.listdir(scores_dir):
        if not fname.endswith(".csv"):
            continue
        field_name = os.path.splitext(fname)[0]
        try:
            wide, meta = load_external_score(os.path.join(scores_dir, fname), field_name, dates, tickers)
            fields[field_name] = wide
            EXTERNAL_FIELD_METADATA[field_name] = meta
            print(f"[external_scores] registered field '{field_name}' from {fname} "
                  f"(aligned on '{meta['availability_column']}')")
        except Exception as e:
            print(f"[external_scores] failed to load {fname}: {e}")
    if fields:
        bump_data_version()
    return fields


# --- Exported from notebook cell 11 ---


def _rolling_apply_lastval(df: pd.DataFrame, window: int, func) -> pd.DataFrame:
    return df.apply(lambda col: col.rolling(window).apply(func, raw=True), axis=0)


def rsi(close, window):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(high, low, close, window):
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).stack(), (high - prev_close).abs().stack(), (low - prev_close).abs().stack(),
    ], axis=1).max(axis=1).unstack()
    return tr.rolling(window).mean()


def macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line - signal_line


def compute_features(ohlcv: dict) -> dict:
    close, high, low, volume = ohlcv["close"], ohlcv["high"], ohlcv["low"], ohlcv["volume"]
    f = {}
    for w in (5, 20, 60):
        f[f"momentum_{w}"] = close / close.shift(w) - 1
    for w in (5, 20, 60):
        f[f"volatility_{w}"] = close.pct_change().rolling(w).std()
    f["rsi_7"] = rsi(close, 7)
    f["rsi_14"] = rsi(close, 14)
    f["atr_14"] = atr(high, low, close, 14)
    for w in (20, 50, 200):
        f[f"sma_{w}"] = close.rolling(w).mean()
    for w in (9, 20, 50):
        f[f"ema_{w}"] = close.ewm(span=w, adjust=False).mean()
    f["macd"] = macd(close)
    for w in (20, 60):
        f[f"volume_ratio_{w}"] = volume / volume.rolling(w).mean()
    return f


# --- Exported from notebook cell 13 ---


# ---------- Arithmetic ----------

def op_abs(x): return x.abs()
def op_inverse(x): return 1.0 / x.replace(0, np.nan)
def op_log(x): return np.log(x.where(x > 0))
def op_sqrt(x): return np.sqrt(x.where(x >= 0))
def op_power(x, y): return x ** y
def op_sign(x): return np.sign(x)
def op_signed_power(x, y): return np.sign(x) * (x.abs() ** y)

def op_min(x, y):
    if isinstance(y, pd.DataFrame):
        return x.where(x <= y, y)
    return x.clip(upper=y)

def op_max(x, y):
    if isinstance(y, pd.DataFrame):
        return x.where(x >= y, y)
    return x.clip(lower=y)

# ---------- Time series ----------

def op_ts_delay(x, d): return x.shift(d)
def op_ts_delta(x, d): return x - x.shift(d)
def op_ts_mean(x, d): return x.rolling(d).mean()
def op_ts_sum(x, d): return x.rolling(d).sum()
def op_ts_std_dev(x, d): return x.rolling(d).std()

def op_ts_rank(x, d):
    def _f(a):
        if np.isnan(a[-1]):
            return np.nan
        valid = a[~np.isnan(a)]
        if len(valid) <= 1:
            return 0.5
        return stats.rankdata(valid)[-1] / len(valid)
    return _rolling_apply_lastval(x, d, _f)

def op_ts_zscore(x, d):
    m, s = x.rolling(d).mean(), x.rolling(d).std()
    return (x - m) / s.replace(0, np.nan)

def op_ts_quantile(x, d):
    return op_ts_rank(x, d)

def op_ts_decay_linear(x, d):
    weights = np.arange(1, d + 1, dtype=float)
    weights /= weights.sum()
    def _f(a):
        if np.isnan(a).any():
            valid_w, valid_a = weights[~np.isnan(a)], a[~np.isnan(a)]
            if valid_w.sum() == 0:
                return np.nan
            return float(np.dot(valid_a, valid_w) / valid_w.sum())
        return float(np.dot(a, weights))
    return _rolling_apply_lastval(x, d, _f)

def op_ts_corr(x, y, d): return x.rolling(d).corr(y)
def op_ts_covariance(x, y, d): return x.rolling(d).cov(y)

def op_ts_arg_max(x, d):
    def _f(a):
        return np.nan if np.isnan(a).all() else float(len(a) - 1 - np.nanargmax(a))
    return _rolling_apply_lastval(x, d, _f)

def op_ts_arg_min(x, d):
    def _f(a):
        return np.nan if np.isnan(a).all() else float(len(a) - 1 - np.nanargmin(a))
    return _rolling_apply_lastval(x, d, _f)

def op_ts_av_diff(x, d): return x - op_ts_mean(x, d)

def op_ts_backfill(x, d, k=1):
    """Fills a NaN with the k-th most recent *valid* value found within the
    trailing d-bar window before it (k=1 = most recent valid value, k=2 =
    second-most-recent, ...). ts_backfill(x, d) == ts_backfill(x, d, k=1) by
    construction (k defaults to 1) — extended per spec; previously this was
    a plain `.ffill(limit=d)`, which is equivalent in spirit for k=1 but
    couldn't express k>1 at all."""
    def _f(a):
        cur = a[-1]
        if not np.isnan(cur):
            return cur
        history = a[:-1]
        valid = history[~np.isnan(history)]
        if len(valid) < k or k < 1:
            return np.nan
        return float(valid[-k])
    return _rolling_apply_lastval(x, d, _f)

def op_ts_product(x, d): return x.rolling(d).apply(lambda a: np.prod(a), raw=True)

def op_ts_regression(y, x, d, rettype="residual"):
    beta = pd.DataFrame(index=y.index, columns=y.columns, dtype=float)
    alpha = pd.DataFrame(index=y.index, columns=y.columns, dtype=float)
    for col in y.columns:
        if col not in x.columns:
            continue
        ys, xs = y[col], x[col]
        cov, var = xs.rolling(d).cov(ys), xs.rolling(d).var()
        b = cov / var.replace(0, np.nan)
        a = ys.rolling(d).mean() - b * xs.rolling(d).mean()
        beta[col], alpha[col] = b, a
    if rettype == "beta":
        return beta
    if rettype == "alpha":
        return alpha
    return y - (alpha + beta * x)

def op_kth_element(x, d, k):
    """ASSUMPTION (no spec attached): k-th most recent *valid* value in the
    trailing d-window; k=1 is the most recent valid value."""
    def _f(a):
        valid = a[~np.isnan(a)]
        if len(valid) < k or k < 1:
            return np.nan
        return float(valid[-k])
    return _rolling_apply_lastval(x, d, _f)

def op_last_diff_value(x, d):
    """ASSUMPTION: most recent value in the trailing d-window that differs
    from the current (last) value; NaN if none found."""
    def _f(a):
        cur = a[-1]
        if np.isnan(cur):
            return np.nan
        for v in a[-2::-1]:
            if not np.isnan(v) and v != cur:
                return float(v)
        return np.nan
    return _rolling_apply_lastval(x, d, _f)

def op_ts_scale(x, d):
    lo, hi = x.rolling(d).min(), x.rolling(d).max()
    return (x - lo) / (hi - lo).replace(0, np.nan)

def op_hump(x, hump_value=0.01):
    """Stateful: dampens the day-to-day change rather than gating it as
    all-or-nothing. If the proposed move exceeds hump_value, the output only
    moves by hump_value in that direction (not straight to the new value);
    below the threshold, the output holds at yesterday's value. E.g.
    previous=1.0, new=1.5, hump_value=0.1 -> 1.1, not 1.5. (Previously this
    let the FULL new value through once the threshold was crossed, which
    isn't the intended dampening behavior — fixed.)"""
    out = pd.DataFrame(np.nan, index=x.index, columns=x.columns)
    prev = pd.Series(np.nan, index=x.columns)
    for d_ in x.index:
        cur = x.loc[d_]
        no_prior = prev.isna()
        delta = cur - prev
        move = delta.abs() > hump_value
        dampened = prev + np.sign(delta) * hump_value
        new_prev = prev.where(~(move & ~no_prior), dampened)
        new_prev = new_prev.where(~no_prior, cur)
        prev = new_prev
        out.loc[d_] = prev
    return out

# ---------- Cross-sectional ----------
# NOTE: these assume the input has already been universe-masked by the
# expression engine (Section 7) — every row here only ever "sees" eligible,
# non-NaN observations, which pandas' skipna default already excludes correctly.

def op_rank(x): return x.rank(axis=1, pct=True)

def op_zscore(x):
    m, s = x.mean(axis=1), x.std(axis=1)
    return x.sub(m, axis=0).div(s.replace(0, np.nan), axis=0)

def op_normalize(x): return x.sub(x.mean(axis=1), axis=0)

def op_quantile_cs(x, buckets=5):
    def _row(row):
        return pd.qcut(row.rank(method="first"), buckets, labels=False, duplicates="drop")
    return x.apply(_row, axis=1)

def op_winsorize(x, std=3.0):
    m, s = x.mean(axis=1), x.std(axis=1)
    return x.clip(lower=m - std * s, upper=m + std * s, axis=0)

def op_scale(x, booksize=1.0):
    denom = x.abs().sum(axis=1).replace(0, np.nan)
    return x.div(denom, axis=0) * booksize

def op_densify(x):
    """ASSUMPTION: row-wise — maps whatever distinct values are present in a
    date\'s cross-section to dense sequential integers 0..k-1, ordered by
    value. Used mainly to compact group/category-like fields."""
    def _row(row):
        valid = row.dropna()
        if valid.empty:
            return row
        mapping = {v: i for i, v in enumerate(sorted(valid.unique()))}
        return row.map(mapping)
    return x.apply(_row, axis=1)

# ---------- Group ----------

def _resolved_group(group_map, columns):
    g = pd.Series(group_map).reindex(columns)
    g = g.fillna("UNKNOWN")
    return g

def op_group_rank(x, group_map):
    def _row(row):
        g = _resolved_group(group_map, row.index)
        return row.groupby(g).rank(pct=True)
    return x.apply(_row, axis=1)

def op_group_zscore(x, group_map):
    def _row(row):
        g = _resolved_group(group_map, row.index)
        gm, gs = row.groupby(g).transform("mean"), row.groupby(g).transform("std")
        return (row - gm) / gs.replace(0, np.nan)
    return x.apply(_row, axis=1)

def op_group_neutralize(x, group_map):
    def _row(row):
        g = _resolved_group(group_map, row.index)
        return row - row.groupby(g).transform("mean")
    return x.apply(_row, axis=1)

def op_group_scale(x, group_map):
    """Group-wise min/max scaling: (x - group_min) / (group_max - group_min),
    independently per date and group. (Previously implemented as
    x / sum(abs(x)) within the group — a different operation, dollar-scaling
    rather than min/max scaling — fixed.) A group with only one valid
    observation, or one where every value is identical, has group_max ==
    group_min: the denominator is 0, so the result is NaN for that group on
    that date (can't min/max-scale a single point or a constant)."""
    def _row(row):
        g = _resolved_group(group_map, row.index)
        gmin = row.groupby(g).transform("min")
        gmax = row.groupby(g).transform("max")
        denom = (gmax - gmin).replace(0, np.nan)
        return (row - gmin) / denom
    return x.apply(_row, axis=1)

def op_group_mean(x, group_map):
    """Audited (Section 4.3 of the hardening pass): each ticker is assigned
    the simple arithmetic mean of its group, per date — this already matches
    the intended semantics (no different weighting or aggregation was
    specified), so kept as-is rather than reimplemented."""
    def _row(row):
        g = _resolved_group(group_map, row.index)
        return row.groupby(g).transform("mean")
    return x.apply(_row, axis=1)

def op_group_backfill(x, d, std=4.0, group_map=None):
    """Fills a missing (t, ticker) value using its GROUP's recent history,
    not the ticker's own history: pool every value from the ticker's group
    over the trailing d days (across all members, all d days), drop NaNs,
    winsorize that pooled sample at `std` standard deviations, and fill with
    the winsorized pool's mean. (Previously: individual ts_backfill first,
    then a same-day group-mean fallback for whatever was still missing —
    that ignores the group's own recent history and has no winsorization,
    so a single outlier in the group could dominate the fill. Fixed.)"""
    dates = x.index
    grp = pd.Series(group_map).reindex(x.columns).fillna("UNKNOWN")
    filled = x.copy()
    for g in grp.unique():
        cols = grp[grp == g].index.tolist()
        sub = x[cols]
        for i, d_ in enumerate(dates):
            missing_today = sub.loc[d_][sub.loc[d_].isna()]
            if missing_today.empty:
                continue
            window = sub.iloc[max(0, i - d + 1): i + 1]
            pooled = window.values.flatten()
            pooled = pooled[~np.isnan(pooled)]
            if len(pooled) == 0:
                continue
            m, s = pooled.mean(), pooled.std()
            if s and s > 0:
                pooled = np.clip(pooled, m - std * s, m + std * s)
            fill_value = float(pooled.mean())
            for col in missing_today.index:
                filled.loc[d_, col] = fill_value
    return filled

# ---------- Logical / conditional ----------

def op_and(x, y): return x.astype(bool) & y.astype(bool)
def op_or(x, y): return x.astype(bool) | y.astype(bool)
def op_not(x): return ~x.astype(bool)
def op_if_else(cond, x, y): return x.where(cond.astype(bool), y)
def op_gt(x, y): return x > y
def op_lt(x, y): return x < y
def op_ge(x, y): return x >= y
def op_le(x, y): return x <= y
def op_eq(x, y): return x == y
def op_ne(x, y): return x != y

# ---------- Transformational ----------

def op_bucket(x, breakpoints):
    def _row(row):
        return pd.cut(row, bins=[-np.inf] + list(breakpoints) + [np.inf], labels=False)
    return x.apply(_row, axis=1)

def op_trade_when(trigger, x, exit_cond):
    """Preserved from v1, audited against Section 14: holds the last value of
    x from the most recent True trigger, carrying it forward as the position,
    until exit_cond fires — at which point the alpha goes to NaN (flat) until
    the next trigger. This is genuinely stateful/path-dependent, evaluated as
    an explicit forward loop rather than a vectorized transform, because a
    vectorized approximation would not correctly capture the "hold until
    exit" persistence Section 14 requires."""
    out = pd.DataFrame(np.nan, index=x.index, columns=x.columns)
    held = pd.Series(np.nan, index=x.columns)
    active = pd.Series(False, index=x.columns)
    for d_ in x.index:
        trig = trigger.loc[d_].astype(bool)
        ex = exit_cond.loc[d_].astype(bool)
        active = (active | trig) & (~ex)
        held = held.where(~trig, x.loc[d_])
        out.loc[d_] = held.where(active, np.nan)
    return out

# ---------- Vector ----------

def op_vec_avg(*fields): return sum(fields) / len(fields)
def op_vec_sum(*fields): return sum(fields)


# --- Exported from notebook cell 15 ---


_EXPR_CACHE = {}

def clear_expression_cache():
    _EXPR_CACHE.clear()

_ALLOWED_NODES = (
    _ast.Expression, _ast.Call, _ast.Name, _ast.Constant, _ast.BinOp, _ast.UnaryOp,
    _ast.USub, _ast.UAdd, _ast.Load, _ast.List, _ast.Tuple, _ast.Add, _ast.Sub,
    _ast.Mult, _ast.Div, _ast.Pow, _ast.Compare, _ast.Gt, _ast.Lt, _ast.GtE,
    _ast.LtE, _ast.Eq, _ast.NotEq, _ast.keyword,
)

_BINOPS = {_ast.Add: _pyop.add, _ast.Sub: _pyop.sub, _ast.Mult: _pyop.mul,
           _ast.Div: _pyop.truediv, _ast.Pow: _pyop.pow}
_CMPOPS = {_ast.Gt: _pyop.gt, _ast.Lt: _pyop.lt, _ast.GtE: _pyop.ge,
           _ast.LtE: _pyop.le, _ast.Eq: _pyop.eq, _ast.NotEq: _pyop.ne}


class AlphaExpressionError(Exception):
    pass


def _check_allowed(node):
    for n in _ast.walk(node):
        if not isinstance(n, _ALLOWED_NODES):
            raise AlphaExpressionError(
                f"Disallowed syntax in expression: {type(n).__name__}. "
                f"Only field names, operator calls, arithmetic, comparisons, "
                f"and literal lists/numbers are permitted."
            )


def _eval_node(node, namespace, cache, cache_ctx):
    if isinstance(node, _ast.Expression):
        return _eval_node(node.body, namespace, cache, cache_ctx)

    if isinstance(node, _ast.Constant):
        return node.value

    if isinstance(node, _ast.List):
        return [_eval_node(e, namespace, cache, cache_ctx) for e in node.elts]

    if isinstance(node, _ast.Tuple):
        return tuple(_eval_node(e, namespace, cache, cache_ctx) for e in node.elts)

    if isinstance(node, _ast.Name):
        if node.id not in namespace:
            available = ", ".join(sorted(k for k in namespace if not callable(namespace[k])))
            raise AlphaExpressionError(
                f"Unknown field or name '{node.id}'. Available fields: {available}"
            )
        val = namespace[node.id]
        if isinstance(val, pd.DataFrame) and cache_ctx.get("universe_mask") is not None:
            key = ("__leaf__", node.id, cache_ctx["key"])
            if key in cache:
                return cache[key]
            masked = val.where(cache_ctx["universe_mask"])
            cache[key] = masked
            return masked
        return val

    if isinstance(node, _ast.UnaryOp):
        operand = _eval_node(node.operand, namespace, cache, cache_ctx)
        if isinstance(node.op, _ast.USub):
            return -operand
        return operand

    if isinstance(node, _ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BINOPS:
            raise AlphaExpressionError(f"Unsupported operator: {op_type.__name__}")
        left = _eval_node(node.left, namespace, cache, cache_ctx)
        right = _eval_node(node.right, namespace, cache, cache_ctx)
        return _BINOPS[op_type](left, right)

    if isinstance(node, _ast.Compare):
        if len(node.ops) != 1:
            raise AlphaExpressionError("Chained comparisons (a < b < c) are not supported — use nested comparisons.")
        left = _eval_node(node.left, namespace, cache, cache_ctx)
        right = _eval_node(node.comparators[0], namespace, cache, cache_ctx)
        op_type = type(node.ops[0])
        if op_type not in _CMPOPS:
            raise AlphaExpressionError(f"Unsupported comparison: {op_type.__name__}")
        return _CMPOPS[op_type](left, right)

    if isinstance(node, _ast.Call):
        if not isinstance(node.func, _ast.Name):
            raise AlphaExpressionError("Only direct operator calls are supported, e.g. rank(x), not attribute/indexed calls.")
        fname = node.func.id
        node_key = ("__call__", _ast.dump(node), cache_ctx["key"])
        if node_key in cache:
            return cache[node_key]
        if fname not in namespace or not callable(namespace[fname]):
            available = ", ".join(sorted(k for k, v in namespace.items() if callable(v)))
            raise AlphaExpressionError(f"Unknown operator '{fname}'. Available operators: {available}")
        fn = namespace[fname]
        args = [_eval_node(a, namespace, cache, cache_ctx) for a in node.args]
        kwargs = {kw.arg: _eval_node(kw.value, namespace, cache, cache_ctx) for kw in node.keywords}
        try:
            result = fn(*args, **kwargs)
        except TypeError as e:
            raise AlphaExpressionError(f"Bad arguments to operator '{fname}': {e}")
        cache[node_key] = result
        return result

    raise AlphaExpressionError(f"Unsupported syntax node: {type(node).__name__}")


def build_namespace(fields: dict, group_map: dict = None) -> dict:
    ns = dict(OPERATORS)
    if group_map is None:
        group_map = {t: "ALL" for t in next(iter(fields.values())).columns}
    for name, fn in GROUP_OPERATORS.items():
        ns[name] = functools.partial(fn, group_map=group_map)
    ns["group_backfill"] = functools.partial(op_group_backfill, group_map=group_map)
    ns.update(fields)
    return ns


def evaluate_expression(expr: str, fields: dict, universe_mask: pd.DataFrame = None,
                         group_map: dict = None) -> pd.DataFrame:
    """Evaluate an alpha expression string. Same syntax as v1; internally now
    an AST interpreter with centralized universe masking and node caching."""
    if not fields:
        raise AlphaExpressionError("No fields available — did you run compute_features()?")
    try:
        tree = _ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise AlphaExpressionError(f"Invalid alpha expression syntax: {e}")
    _check_allowed(tree)

    namespace = build_namespace(fields, group_map)
    any_field = next(iter(fields.values()))
    context_key = (
        expr, _DATA_VERSION,
        id(universe_mask) if universe_mask is not None else None,
        str(any_field.index.min()), str(any_field.index.max()),
    )
    cache_ctx = {"universe_mask": universe_mask, "key": context_key}

    result = _eval_node(tree, namespace, _EXPR_CACHE, cache_ctx)

    if not isinstance(result, pd.DataFrame):
        raise AlphaExpressionError(
            f"Alpha expression must evaluate to a (date x ticker) DataFrame, got {type(result).__name__}."
        )
    if universe_mask is not None:
        result = result.where(universe_mask)
    if universe_mask is not None and (universe_mask.sum(axis=1) == 0).all():
        raise AlphaExpressionError("Universe mask is empty on every date — check universe construction.")
    return result

OPERATORS = {
    "abs": op_abs, "inverse": op_inverse, "log": op_log, "sqrt": op_sqrt,
    "power": op_power, "sign": op_sign, "signed_power": op_signed_power,
    "min": op_min, "max": op_max,
    "ts_delay": op_ts_delay, "ts_delta": op_ts_delta, "ts_mean": op_ts_mean,
    "ts_sum": op_ts_sum, "ts_std_dev": op_ts_std_dev, "ts_rank": op_ts_rank,
    "ts_zscore": op_ts_zscore, "ts_quantile": op_ts_quantile,
    "ts_decay_linear": op_ts_decay_linear, "ts_corr": op_ts_corr,
    "ts_covariance": op_ts_covariance, "ts_arg_max": op_ts_arg_max,
    "ts_arg_min": op_ts_arg_min, "ts_av_diff": op_ts_av_diff,
    "ts_backfill": op_ts_backfill, "ts_product": op_ts_product,
    "ts_regression": op_ts_regression, "kth_element": op_kth_element,
    "last_diff_value": op_last_diff_value, "ts_scale": op_ts_scale, "hump": op_hump,
    "rank": op_rank, "zscore": op_zscore, "normalize": op_normalize,
    "quantile": op_quantile_cs, "winsorize": op_winsorize, "scale": op_scale,
    "densify": op_densify,
    "and_": op_and, "or_": op_or, "not_": op_not, "if_else": op_if_else,
    "gt": op_gt, "lt": op_lt, "ge": op_ge, "le": op_le, "eq": op_eq, "ne": op_ne,
    "bucket": op_bucket, "trade_when": op_trade_when,
    "vec_avg": op_vec_avg, "vec_sum": op_vec_sum,
}
GROUP_OPERATORS = {
    "group_rank": op_group_rank, "group_zscore": op_group_zscore,
    "group_neutralize": op_group_neutralize, "group_scale": op_group_scale,
    "group_mean": op_group_mean,
}


# --- Exported from notebook cell 17 ---


def align_signal_to_execution(alpha: pd.DataFrame, execution_lag_bars: int = None) -> pd.DataFrame:
    lag = CONFIG["execution"]["execution_lag_bars"] if execution_lag_bars is None else execution_lag_bars
    return alpha.shift(lag)


def get_execution_price(ohlcv: dict, execution_price: str = None) -> pd.DataFrame:
    which = CONFIG["execution"]["execution_price"] if execution_price is None else execution_price
    if which not in ("close", "open"):
        raise ValueError(f"execution_price must be 'close' or 'open', got {which!r}")
    return ohlcv[which]


def compute_forward_returns(price: pd.DataFrame, holding_period: int = 1) -> pd.DataFrame:
    """Forward return over `holding_period` bars, measured FROM the
    already-actionable date (i.e. call this on alpha_actionable\'s date axis
    — the execution lag has already been applied upstream, so this function
    only needs to know the holding period, not the lag)."""
    return price.shift(-holding_period) / price - 1


# --- Exported from notebook cell 19 ---


PORTFOLIO_TYPES = {"LONG_SHORT", "LONG_ONLY", "TOP_K", "BOTTOM_K", "TOP_BOTTOM", "QUANTILE"}
WEIGHTING_SCHEMES = {"EQUAL_WEIGHT", "SIGNAL_WEIGHTED", "RANK_WEIGHTED", "NORMALIZED_SIGNAL"}


def _leg_weights(values: pd.Series, weighting: str, *, short_leg: bool = False) -> pd.Series:
    """Return normalized positive weights for one selected portfolio leg.

    For rank weighting, the most extreme names receive the largest weights
    on BOTH sides: highest alpha on the long leg and lowest alpha on the
    short leg. This makes a symmetric long/short book invariant to negating
    the alpha (the long and short legs exchange places).
    """
    values = values.dropna()
    if values.empty:
        return values
    if weighting == "EQUAL_WEIGHT":
        w = pd.Series(1.0, index=values.index)
    elif weighting == "SIGNAL_WEIGHTED":
        w = values.abs()
    elif weighting == "RANK_WEIGHTED":
        w = values.rank(ascending=not short_leg, method="average")
    elif weighting == "NORMALIZED_SIGNAL":
        std = values.std()
        z = (values - values.mean()) / std if pd.notna(std) and std > 0 else pd.Series(0.0, index=values.index)
        w = z.abs()
    else:
        raise ValueError(f"Unknown weighting scheme: {weighting}. Expected one of {WEIGHTING_SCHEMES}")
    total = w.sum()
    return w / total if total else w


def construct_portfolio_row(alpha_row: pd.Series, portfolio_type: str, weighting: str,
                             n_buckets: int = 5, k: int = 10, quantile_index: int = None,
                             long_exposure: float = 1.0, short_exposure: float = 1.0,
                             max_position_weight: float = None) -> pd.Series:
    """Given one date's alpha values, return a weights Series (same index),
    positive = long, negative = short, summing to the requested exposures."""
    if portfolio_type not in PORTFOLIO_TYPES:
        raise ValueError(f"Unknown portfolio_type: {portfolio_type}. Expected one of {PORTFOLIO_TYPES}")
    a = alpha_row.dropna()
    weights = pd.Series(0.0, index=alpha_row.index)
    if a.empty:
        return weights

    if portfolio_type in ("LONG_SHORT", "TOP_BOTTOM", "TOP_K", "BOTTOM_K", "QUANTILE"):
        # Resolve ties in a sign-symmetric way. The orientation marker flips
        # when the entire alpha is negated; reversing the stable ticker order
        # at the same time makes ranked(-a) exactly n + 1 - ranked(a), even
        # when alpha values contain ties (e.g. rank(x) outputs).
        nonzero = a[a != 0]
        orientation = float(np.sign(nonzero.iloc[0])) if not nonzero.empty else 1.0
        rank_input = a if orientation >= 0 else a.iloc[::-1]
        ranked = rank_input.rank(method="first").reindex(a.index)
        n = len(a)
        if portfolio_type == "QUANTILE":
            bucket_id = pd.qcut(ranked, n_buckets, labels=False, duplicates="drop")
            qi = n_buckets - 1 if quantile_index is None else quantile_index
            sel = a[bucket_id == qi]
            w = _leg_weights(sel, weighting) * long_exposure
            weights.loc[w.index] = w
        else:
            if portfolio_type in ("LONG_SHORT", "TOP_BOTTOM"):
                bucket_id = pd.qcut(ranked, n_buckets, labels=False, duplicates="drop") if portfolio_type == "LONG_SHORT" else None
                if portfolio_type == "LONG_SHORT":
                    long_sel = a[bucket_id == bucket_id.max()]
                    short_sel = a[bucket_id == bucket_id.min()]
                else:  # TOP_BOTTOM — explicit K, not quantile fraction
                    long_sel = a.loc[ranked.nlargest(min(k, len(a))).index]
                    short_sel = a.loc[ranked.nsmallest(min(k, len(a))).index]
                lw = _leg_weights(long_sel, weighting) * long_exposure
                sw = _leg_weights(short_sel, weighting, short_leg=True) * short_exposure
                weights.loc[lw.index] = lw
                weights.loc[sw.index] -= sw
            elif portfolio_type == "TOP_K":
                sel = a.loc[ranked.nlargest(min(k, len(a))).index]
                w = _leg_weights(sel, weighting) * long_exposure
                weights.loc[w.index] = w
            elif portfolio_type == "BOTTOM_K":
                sel = a.loc[ranked.nsmallest(min(k, len(a))).index]
                w = _leg_weights(sel, weighting, short_leg=True) * short_exposure
                weights.loc[w.index] = -w
    elif portfolio_type == "LONG_ONLY":
        positive = a[a > 0]
        w = _leg_weights(positive, weighting) * long_exposure
        weights.loc[w.index] = w

    if max_position_weight is not None:
        weights = weights.clip(lower=-max_position_weight, upper=max_position_weight)
        # one renormalization pass after clipping — approximate, documented (Section 5)
        gross = weights.abs().sum()
        target_gross = long_exposure + short_exposure
        if gross > 0 and gross > target_gross:
            weights = weights * (target_gross / gross)

    return weights


def build_staggered_weights(alpha_actionable: pd.DataFrame, holding_period: int, **portfolio_kwargs) -> pd.DataFrame:
    """Splits dates into `holding_period` interleaved cohorts; each cohort
    only rebalances every holding_period bars (so no single cohort double-
    counts an overlapping window), then blends the cohorts\' currently-held
    weights (each contributing 1/holding_period of book) into one daily
    weights matrix. Standard staggered/tranche technique for backtesting
    multi-day holding periods without inflating apparent Sharpe from
    overlapping daily rebalances (Section 4/28)."""
    dates = alpha_actionable.index
    weights = pd.DataFrame(0.0, index=dates, columns=alpha_actionable.columns)
    for cohort in range(holding_period):
        rebal_dates = set(dates[cohort::holding_period])
        current_w = pd.Series(0.0, index=alpha_actionable.columns)
        for d in dates:
            if d in rebal_dates:
                current_w = construct_portfolio_row(alpha_actionable.loc[d], **portfolio_kwargs)
            weights.loc[d] += current_w.reindex(alpha_actionable.columns).fillna(0.0) / holding_period
    return weights


def compute_turnover_series(weights: pd.DataFrame) -> pd.Series:
    return weights.diff().abs().sum(axis=1) / 2


def apply_costs(gross_returns: pd.Series, turnover: pd.Series, transaction_cost_bps: float,
                 slippage_bps: float) -> tuple:
    cost_rate = (transaction_cost_bps + slippage_bps) / 10000.0
    costs = turnover * cost_rate
    net_returns = gross_returns - costs
    return net_returns, costs


def run_staggered_backtest(alpha_actionable: pd.DataFrame, execution_price: pd.DataFrame,
                            holding_period: int, portfolio_type: str, weighting: str,
                            transaction_cost_bps: float, slippage_bps: float,
                            **portfolio_kwargs) -> dict:
    """Core engine: weights -> gross/net daily returns + turnover, using the
    staggered cohort weights from build_staggered_weights()."""
    weights = build_staggered_weights(alpha_actionable, holding_period, portfolio_type=portfolio_type,
                                       weighting=weighting, **portfolio_kwargs)
    asset_returns = execution_price.pct_change()
    gross_returns = (weights.shift(1).fillna(0.0) * asset_returns).sum(axis=1)
    turnover = compute_turnover_series(weights)
    net_returns, costs = apply_costs(gross_returns, turnover, transaction_cost_bps, slippage_bps)
    return {
        "weights": weights, "gross_returns": gross_returns, "net_returns": net_returns,
        "turnover": turnover, "costs": costs,
    }


# --- Exported from notebook cell 21 ---


def compute_daily_ic(alpha: pd.DataFrame, fwd_returns: pd.DataFrame, method: str = "spearman") -> pd.Series:
    ic = {}
    for d in alpha.index:
        if d not in fwd_returns.index:
            continue
        a, r = alpha.loc[d], fwd_returns.loc[d]
        both = pd.concat([a, r], axis=1).dropna()
        if len(both) < 5:
            continue
        if method == "spearman":
            rho, _ = stats.spearmanr(both.iloc[:, 0], both.iloc[:, 1])
        elif method == "pearson":
            rho, _ = stats.pearsonr(both.iloc[:, 0], both.iloc[:, 1])
        else:
            raise ValueError("method must be 'spearman' or 'pearson'")
        ic[d] = rho
    return pd.Series(ic).sort_index()


def ic_diagnostics(ic_series: pd.Series) -> dict:
    clean = ic_series.dropna()
    if clean.empty:
        return {"ic_mean": np.nan, "ic_std": np.nan, "ic_ir": np.nan, "pct_positive": np.nan}
    return {
        "ic_mean": float(clean.mean()),
        "ic_std": float(clean.std()),
        "ic_ir": float(clean.mean() / clean.std()) if clean.std() else np.nan,
        "pct_positive": float((clean > 0).mean()),
        "rolling_ic_20d": clean.rolling(20).mean(),
        "ic_by_year": clean.groupby(clean.index.year).mean(),
        "ic_by_month": clean.groupby([clean.index.year, clean.index.month]).mean(),
    }


# --- Exported from notebook cell 23 ---


def annualize_return(returns: pd.Series, periods_per_year: int = 252) -> float:
    return float(returns.mean() * periods_per_year)

def annualize_vol(returns: pd.Series, periods_per_year: int = 252) -> float:
    return float(returns.std() * np.sqrt(periods_per_year))

def sharpe_ratio(returns: pd.Series, rf_annual: float = 0.0, periods_per_year: int = 252) -> float:
    excess = returns - rf_annual / periods_per_year
    vol = excess.std()
    return float(excess.mean() / vol * np.sqrt(periods_per_year)) if vol else np.nan

def sortino_ratio(returns: pd.Series, rf_annual: float = 0.0, periods_per_year: int = 252) -> float:
    excess = returns.dropna() - rf_annual / periods_per_year
    if excess.empty:
        return np.nan
    # Downside deviation is the root-mean-square of ALL observations after
    # clipping positive excess returns to zero (not the std of negative days).
    downside = np.minimum(excess.to_numpy(dtype=float), 0.0)
    downside_deviation = float(np.sqrt(np.mean(np.square(downside))))
    return float(excess.mean() / downside_deviation * np.sqrt(periods_per_year)) if downside_deviation > 0 else np.nan

def max_drawdown_series(cum_returns: pd.Series) -> pd.Series:
    running_max = cum_returns.cummax()
    return cum_returns / running_max - 1

def drawdown_stats(cum_returns: pd.Series, top_n: int = 3) -> dict:
    dd = max_drawdown_series(cum_returns)
    max_dd = float(dd.min())
    trough = dd.idxmin()
    pre_trough = dd.loc[:trough]
    peak = pre_trough[pre_trough == 0].index.max() if (pre_trough == 0).any() else dd.index[0]
    post_trough = dd.loc[trough:]
    recovery = post_trough[post_trough >= 0].index.min() if (post_trough >= 0).any() else None
    duration = (trough - peak).days if peak is not None else None
    recovery_time = (recovery - trough).days if recovery is not None else None

    # top-N distinct drawdown episodes by depth
    episodes, in_dd, start = [], False, None
    for d_, v in dd.items():
        if v < 0 and not in_dd:
            in_dd, start = True, d_
        elif v >= 0 and in_dd:
            in_dd = False
            episodes.append((start, d_, dd.loc[start:d_].min()))
    if in_dd:
        episodes.append((start, dd.index[-1], dd.loc[start:].min()))
    episodes.sort(key=lambda e: e[2])

    return {
        "max_drawdown": max_dd, "drawdown_duration_days": duration,
        "recovery_time_days": recovery_time,
        "top_drawdowns": episodes[:top_n], "drawdown_series": dd,
    }

def calmar_ratio(ann_return: float, max_dd: float) -> float:
    return float(ann_return / abs(max_dd)) if max_dd else np.nan

def win_rate(returns: pd.Series) -> float:
    nz = returns[returns != 0]
    return float((nz > 0).mean()) if len(nz) else np.nan

def profit_factor(returns: pd.Series) -> float:
    gains, losses = returns[returns > 0].sum(), -returns[returns < 0].sum()
    return float(gains / losses) if losses else np.nan


# --- Exported from notebook cell 25 ---


def quantile_analysis(alpha: pd.DataFrame, fwd_returns: pd.DataFrame, n_buckets: int = 10) -> pd.DataFrame:
    records = []
    for d in alpha.index:
        if d not in fwd_returns.index:
            continue
        a, r = alpha.loc[d].dropna(), fwd_returns.loc[d]
        if len(a) < n_buckets * 2:
            continue
        both = pd.concat([a, r.reindex(a.index)], axis=1).dropna()
        both.columns = ["alpha", "fwd_ret"]
        if len(both) < n_buckets * 2:
            continue
        both["bucket"] = pd.qcut(both["alpha"].rank(method="first"), n_buckets, labels=False, duplicates="drop")
        for b, grp in both.groupby("bucket"):
            records.append({"date": d, "bucket": b, "avg_return": grp["fwd_ret"].mean()})
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=["bucket", "avg_return", "cumulative_return"])
    summary = df.groupby("bucket")["avg_return"].mean().to_frame("avg_return")
    for b in summary.index:
        bucket_returns = df[df["bucket"] == b].set_index("date")["avg_return"]
        summary.loc[b, "cumulative_return"] = float((1 + bucket_returns.fillna(0)).prod() - 1)
    return summary

def quantile_monotonicity(quantile_summary: pd.DataFrame) -> float:
    if len(quantile_summary) < 3:
        return np.nan
    rho, _ = stats.spearmanr(quantile_summary.index, quantile_summary["avg_return"])
    return float(rho)


# --- Exported from notebook cell 27 ---


def benchmark_analysis(portfolio_returns: pd.Series, benchmark_price: pd.Series) -> dict:
    if benchmark_price is None or benchmark_price.dropna().empty:
        return {"available": False}
    bench_returns = benchmark_price.pct_change().reindex(portfolio_returns.index)
    both = pd.concat([portfolio_returns, bench_returns], axis=1).dropna()
    both.columns = ["port", "bench"]
    if len(both) < 10:
        return {"available": False}
    excess = both["port"] - both["bench"]
    cov = both["port"].cov(both["bench"])
    var = both["bench"].var()
    beta = cov / var if var else np.nan
    corr = both["port"].corr(both["bench"])
    tracking_error = excess.std() * np.sqrt(252)
    ir = (excess.mean() * 252) / tracking_error if tracking_error else np.nan
    return {
        "available": True, "beta": float(beta), "correlation": float(corr),
        "tracking_error": float(tracking_error), "information_ratio": float(ir),
        "annualized_excess_return": float(excess.mean() * 252),
        "benchmark_annual_return": float(both["bench"].mean() * 252),
    }


def exposure_series(weights: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "long_exposure": weights.clip(lower=0).sum(axis=1),
        "short_exposure": weights.clip(upper=0).abs().sum(axis=1),
        "gross_exposure": weights.abs().sum(axis=1),
        "net_exposure": weights.sum(axis=1),
    })


def sector_exposure(weights: pd.DataFrame, group_map: dict) -> pd.DataFrame:
    grp = pd.Series(group_map).reindex(weights.columns).fillna("UNKNOWN")
    return weights.T.groupby(grp).sum().T


def compute_factor_returns(fields: dict, universe_mask: pd.DataFrame, feature_name: str,
                            n_buckets: int = 5) -> pd.Series:
    factor_alpha = fields[feature_name].where(universe_mask)
    weights = factor_alpha.apply(
        lambda row: construct_portfolio_row(row, "LONG_SHORT", "EQUAL_WEIGHT", n_buckets=n_buckets), axis=1
    )
    asset_returns = fields["close"].pct_change()
    return (weights.shift(1).fillna(0.0) * asset_returns).sum(axis=1)


def factor_exposure_analysis(portfolio_returns: pd.Series, fields: dict, universe_mask: pd.DataFrame) -> dict:
    exposures = {}
    for feat in ("momentum_20", "volatility_20"):
        if feat not in fields:
            continue
        factor_ret = compute_factor_returns(fields, universe_mask, feat)
        both = pd.concat([portfolio_returns, factor_ret], axis=1).dropna()
        both.columns = ["port", "factor"]
        if len(both) < 10:
            continue
        cov, var = both["port"].cov(both["factor"]), both["factor"].var()
        exposures[feat] = float(cov / var) if var else np.nan
    return exposures


# --- Exported from notebook cell 29 ---


def data_quality_report(ohlcv: dict) -> pd.DataFrame:
    close = ohlcv["close"]
    rows = []
    for ticker in close.columns:
        s = close[ticker]
        vol = ohlcv["volume"][ticker]
        returns = s.pct_change()
        rows.append({
            "ticker": ticker,
            "n_obs": int(s.notna().sum()),
            "missing_pct": float(s.isna().mean()),
            "duplicate_dates": int(close.index.duplicated().sum()),
            "negative_or_zero_price_days": int((s <= 0).sum()),
            "extreme_return_days_gt_50pct": int((returns.abs() > 0.5).sum()),
            "zero_volume_days": int((vol == 0).sum()),
            "insufficient_history": bool(s.notna().sum() < 60),
        })
    report = pd.DataFrame(rows).set_index("ticker")
    report.attrs["duplicate_tickers"] = int(close.columns.duplicated().sum())
    return report


def coverage_diagnostics(alpha: pd.DataFrame) -> dict:
    valid = alpha.notna()
    by_date = valid.mean(axis=1)
    by_ticker = valid.mean(axis=0)
    return {
        "avg_coverage": float(by_date.mean()),
        "min_coverage": float(by_date.min()),
        "coverage_by_date": by_date,
        "coverage_by_ticker": by_ticker,
    }


# --- Exported from notebook cell 31 ---


import sys as _sys

@dataclass
class BacktestResult:
    expression: str
    universe: str
    universe_metadata: dict
    start_date: str
    end_date: str
    holding_period: int
    execution_config: dict
    portfolio_type: str
    weighting: str
    cost_assumptions: dict

    ic_mean: float
    ic_std: float
    ic_ir: float
    pct_positive_ic: float
    sharpe_gross: float
    sharpe_net: float
    sortino: float
    calmar: float
    annual_return_gross: float
    annual_return_net: float
    annual_vol: float
    max_drawdown: float
    drawdown_duration_days: object
    win_rate: float
    profit_factor: float
    turnover_mean: float
    turnover_annual: float

    long_exposure_mean: float
    short_exposure_mean: float
    gross_exposure_mean: float
    net_exposure_mean: float

    benchmark: dict
    factor_exposures: dict

    coverage: dict
    survivorship_bias_risk: bool

    # time series, kept for plotting / further analysis
    ic_series: pd.Series
    gross_returns: pd.Series
    net_returns: pd.Series
    cum_gross_returns: pd.Series
    cum_net_returns: pd.Series
    turnover_series: pd.Series
    drawdown_series: pd.Series
    exposures: pd.DataFrame
    quantile_summary: pd.DataFrame

    metadata: dict = dc_field(default_factory=dict)

    def summary(self) -> pd.Series:
        keys = ["expression", "universe", "holding_period", "portfolio_type", "weighting",
                "ic_mean", "ic_ir", "sharpe_gross", "sharpe_net", "annual_return_net",
                "annual_vol", "max_drawdown", "turnover_annual", "win_rate", "profit_factor",
                "survivorship_bias_risk"]
        return pd.Series({k: getattr(self, k) for k in keys})

    # --- Production JSON contract -----------------------------------------
    def to_dict(self) -> dict:
        """Return a strict JSON-native representation of every result field."""
        def _ser(v):
            if v is pd.NA or v is pd.NaT:
                return None
            if v is None or isinstance(v, (str, bool, int)):
                return v
            if isinstance(v, (float, np.floating)):
                x = float(v)
                return x if np.isfinite(x) else None
            if isinstance(v, np.generic):
                return _ser(v.item())
            if isinstance(v, (pd.Timestamp, datetime)):
                if pd.isna(v):
                    return None
                return v.isoformat()
            if isinstance(v, pd.Timedelta):
                return v.isoformat()
            if isinstance(v, pd.Series):
                return {str(k): _ser(x) for k, x in v.items()}
            if isinstance(v, pd.DataFrame):
                return {str(idx): {str(c): _ser(x) for c, x in row.items()}
                        for idx, row in v.iterrows()}
            if isinstance(v, dict):
                return {str(k): _ser(x) for k, x in v.items()}
            if isinstance(v, (list, tuple)):
                return [_ser(x) for x in v]
            if isinstance(v, np.ndarray):
                return _ser(v.tolist())
            if isinstance(v, (set, frozenset)):
                return [_ser(x) for x in sorted(v, key=repr)]
            raise TypeError(f"Unsupported result value for JSON serialization: {type(v).__name__}")

        return {f: _ser(getattr(self, f)) for f in self.__dataclass_fields__}

    def to_json(self, **json_kwargs) -> str:
        """Serialize without a fallback encoder: unsupported values must fail loudly."""
        json_kwargs.setdefault("allow_nan", False)
        return json.dumps(self.to_dict(), **json_kwargs)


# --- Exported from notebook cell 33 ---


def check_same_day_leakage(alpha_actionable: pd.DataFrame, close: pd.DataFrame,
                            universe_mask: pd.DataFrame) -> dict:
    fwd = compute_forward_returns(close, 1).where(universe_mask)
    same_day = close.pct_change().where(universe_mask)
    fwd_ic = compute_daily_ic(alpha_actionable, fwd).mean()
    same_day_ic = compute_daily_ic(alpha_actionable, same_day).mean()
    return {
        "forward_ic": float(fwd_ic), "same_day_ic": float(same_day_ic),
        "suspicious": bool(abs(same_day_ic) > abs(fwd_ic) * 2 and abs(same_day_ic) > 0.05),
    }


def synthetic_leakage_ground_truth_test(n_dates: int = 200, n_tickers: int = 20, seed: int = 42) -> dict:
    """Builds a fake dataset where 'cheat_feature' at date t is EXACTLY the
    return realized from t to t+1 (i.e. a perfect leak if used unlagged).
    Confirms: (a) with execution_lag_bars=0, evaluating the raw feature as
    the alpha against the next-day forward return gives IC ~ 1.0 (the leak
    IS present and IS detected by IC, proving the test dataset is a valid
    leak fixture) and (b) with execution_lag_bars=1 (align_signal_to_execution
    applied), that same near-perfect IC collapses toward 0 — proving the lag
    mechanism actually removes a real leak rather than just looking correct."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_dates)
    tickers = [f"SYN{i}" for i in range(n_tickers)]
    rets = rng.normal(0, 0.02, size=(n_dates, n_tickers))
    price = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates, columns=tickers)
    mask = pd.DataFrame(True, index=dates, columns=tickers)

    true_fwd_return = compute_forward_returns(price, 1)
    cheat_feature = true_fwd_return.copy()  # the leak: today's row IS tomorrow's return

    unlagged_ic = compute_daily_ic(cheat_feature.where(mask), true_fwd_return.where(mask)).mean()
    lagged_feature = align_signal_to_execution(cheat_feature, execution_lag_bars=1)
    lagged_ic = compute_daily_ic(lagged_feature.where(mask), true_fwd_return.where(mask)).mean()

    return {
        "unlagged_ic_with_known_leak": float(unlagged_ic),
        "lagged_ic_with_same_leak": float(lagged_ic),
        "leak_correctly_detected": bool(abs(unlagged_ic) > 0.8),
        "lag_correctly_removes_leak": bool(abs(lagged_ic) < 0.2),
    }


# --- Exported from notebook cell 35 ---


def effective_n(n_obs: int, holding_period: int) -> float:
    """Overlapping holding-period observations aren\'t independent — approximate
    effective sample size as n / holding_period (a standard, if simplified,
    correction; a full Newey-West correction would be more rigorous but is not
    implemented here — see Section Z limitations)."""
    return max(n_obs / max(holding_period, 1), 1)

def ic_confidence_interval(ic_series: pd.Series, holding_period: int, conf: float = 0.95) -> dict:
    clean = ic_series.dropna()
    n_eff = effective_n(len(clean), holding_period)
    se = clean.std() / np.sqrt(n_eff) if n_eff > 1 else np.nan
    z = stats.norm.ppf(1 - (1 - conf) / 2)
    mean = clean.mean()
    return {"mean": float(mean), "se": float(se), "n_obs": len(clean), "n_effective": float(n_eff),
            "ci_low": float(mean - z * se) if se == se else np.nan,
            "ci_high": float(mean + z * se) if se == se else np.nan}

def sharpe_standard_error(sharpe: float, n_obs: int) -> float:
    if n_obs <= 1 or sharpe != sharpe:
        return np.nan
    return float(np.sqrt((1 + 0.5 * sharpe ** 2) / n_obs))


class ExperimentTracker:
    """Logs every run_backtest() call so repeated tweak-and-rerun sessions get
    an explicit warning about multiple-testing / overfitting risk (Section 37)
    rather than silently letting the researcher cherry-pick the best of many
    tries.

    Persistence boundary (P1, API-fix pass): `save()`/`load()` below write a
    single plain JSON file. This is intentionally minimal -- explicit,
    file-based, in-process persistence for one researcher's notebook
    session. It is NOT a database: there is no locking, no concurrent-writer
    safety (two kernels/processes `save()`-ing to the same path can clobber
    each other), and no per-user scoping (the log is whatever is in `self.log`
    for whoever is holding this Python object). If multiple concurrent users
    or processes need to track experiments, that calls for a real database
    or job store -- deliberately not built here per the "don't introduce a
    database unless necessary" instruction; this is the minimal practical
    interface for a single-session research tool."""
    def __init__(self):
        self.log = []

    def record(self, expression: str, params: dict, status: str = "success",
               error: str = None, result_summary: dict = None, experiment_id: str = None):
        # P5 (V2 finalize pass): status/error/result_summary/experiment_id are
        # optional and default so the original run_backtest() call site
        # (`TRACKER.record(expression, params)`) keeps working unchanged --
        # this only adds the ability to also log failed/validated runs via
        # record_failure(), a richer success summary, and a canonical
        # experiment_id (API-fix pass, P1 item 3) so a tracker row can be
        # tied back to the exact id a caller of run_backtest_api() got in
        # its response, without touching run_backtest()'s own signature.
        self.log.append({
            "experiment_id": experiment_id, "expression": expression, "params": dict(params),
            "at": datetime.now(), "status": status, "error": error, "result_summary": result_summary,
        })

    def record_failure(self, expression: str, params: dict, error: Exception, experiment_id: str = None):
        self.record(expression, params, status="error", error=str(error), experiment_id=experiment_id)

    def get(self, experiment_id: str) -> dict:
        """Look up a logged entry by the canonical experiment_id (API-fix
        pass, P1 item 3) -- the same id returned in run_backtest_api()'s
        response and used as the tracker record's own id, so a result can be
        traced back to its log entry (and vice versa) without guessing.
        Returns None if no entry with that id was logged this session."""
        for row in reversed(self.log):
            if row.get("experiment_id") == experiment_id:
                return row
        return None

    def count(self) -> int:
        return len(self.log)

    def warn_if_needed(self):
        n = self.count()
        threshold = CONFIG["overfitting_warning_threshold"]
        if n >= threshold:
            print(f"[ExperimentTracker] WARNING: {n} experiments logged this session "
                  f"(threshold {threshold}). Selecting the best-looking result out of many "
                  f"tried is a classic overfitting/multiple-testing trap — a high Sharpe/IC "
                  f"found this way is weaker evidence than the same number found on the FIRST try. "
                  f"This is a research tool, not proof of predictive validity.")

    def summary(self) -> pd.DataFrame:
        return pd.DataFrame(self.log)

    # --- P5 (V2 finalize pass): serialize / persist / recover -------------
    def to_dict(self) -> list:
        out = []
        for row in self.log:
            r = dict(row)
            r["at"] = r["at"].isoformat() if hasattr(r["at"], "isoformat") else str(r["at"])
            # This helper is defined at the API boundary later in the notebook;
            # fall back to strict primitive conversion if used before that cell.
            if "_json_safe" in globals():
                r = _json_safe(r)
            out.append(r)
        return out

    def save(self, path: str):
        """Atomically persist this process's log as strict JSON.

        This avoids partially-written files on interruption. It does not
        provide multi-process locking or replace a database for concurrent users.
        """
        import os
        import tempfile
        directory = os.path.dirname(os.path.abspath(path))
        fd, tmp_path = tempfile.mkstemp(prefix=".experiment-log-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.to_dict(), fh, indent=2, allow_nan=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def load(self, path: str, replace: bool = True):
        """Recover a previously-saved log. `replace=True` (default) replaces
        this tracker's in-memory log; `replace=False` appends to it."""
        with open(path, "r") as fh:
            rows = json.load(fh)
        for r in rows:
            if isinstance(r.get("at"), str):
                try:
                    r["at"] = datetime.fromisoformat(r["at"])
                except ValueError:
                    pass
        if replace:
            self.log = rows
        else:
            self.log.extend(rows)
        return self


TRACKER = ExperimentTracker()


# --- Exported from notebook cell 37 ---


def split_dates(dates: pd.DatetimeIndex, train_frac: float = 0.6, val_frac: float = 0.2):
    n = len(dates)
    train_end, val_end = int(n * train_frac), int(n * (train_frac + val_frac))
    return dates[:train_end], dates[train_end:val_end], dates[val_end:]


def evaluate_train_val_test(run_backtest_fn, **kwargs) -> pd.DataFrame:
    """Chronological only, per Section 30 — runs the SAME configuration on
    three non-overlapping, time-ordered slices via explicit start/end dates
    rather than randomly splitting rows."""
    start, end = pd.Timestamp(kwargs["start"]), pd.Timestamp(kwargs["end"])
    full_range = pd.bdate_range(start, end)
    train, val, test = split_dates(full_range)
    rows = {}
    for label, dates in [("train", train), ("val", val), ("test", test)]:
        if len(dates) < 30:
            continue
        sub_kwargs = dict(kwargs)
        sub_kwargs["start"], sub_kwargs["end"] = str(dates[0].date()), str(dates[-1].date())
        sub_kwargs["_skip_tracker"] = True
        result = run_backtest_fn(**sub_kwargs)
        rows[label] = result.summary()
    return pd.DataFrame(rows).T


def walk_forward(run_backtest_fn, window_days: int = 252, step_days: int = 63,
                  expanding: bool = False, **kwargs) -> pd.DataFrame:
    start, end = pd.Timestamp(kwargs["start"]), pd.Timestamp(kwargs["end"])
    all_dates = pd.bdate_range(start, end)
    rows = []
    win_start_idx = 0
    while True:
        win_start = 0 if expanding else win_start_idx
        win_end_idx = win_start_idx + window_days
        if win_end_idx > len(all_dates):
            break
        window_dates = all_dates[win_start:win_end_idx]
        sub_kwargs = dict(kwargs)
        sub_kwargs["start"], sub_kwargs["end"] = str(window_dates[0].date()), str(window_dates[-1].date())
        sub_kwargs["_skip_tracker"] = True
        try:
            result = run_backtest_fn(**sub_kwargs)
            rows.append({"window_start": window_dates[0], "window_end": window_dates[-1],
                         "ic_mean": result.ic_mean, "sharpe_net": result.sharpe_net,
                         "turnover_annual": result.turnover_annual})
        except Exception as e:
            rows.append({"window_start": window_dates[0], "window_end": window_dates[-1], "error": str(e)})
        win_start_idx += step_days
    return pd.DataFrame(rows)


# --- Exported from notebook cell 39 ---


def run_backtest(expression: str, universe: str, start: str, end: str,
                  holding_period: int = None, portfolio: str = "LONG_SHORT", weighting: str = "EQUAL_WEIGHT",
                  transaction_cost_bps: float = None, slippage_bps: float = None,
                  execution_lag_bars: int = None, execution_price: str = None,
                  n_buckets: int = None, k: int = 10, max_position_weight: float = None,
                  long_exposure: float = 1.0, short_exposure: float = 1.0,
                  group_map: dict = None, ohlcv: dict = None, fields: dict = None,
                  market_cap: pd.DataFrame = None, universe_mask_and_meta: tuple = None,
                  benchmark_price: pd.Series = None,
                  _skip_tracker: bool = False) -> BacktestResult:

    holding_period = CONFIG["holding_period"] if holding_period is None else holding_period
    transaction_cost_bps = CONFIG["transaction_cost_bps"] if transaction_cost_bps is None else transaction_cost_bps
    slippage_bps = CONFIG["slippage_bps"] if slippage_bps is None else slippage_bps
    n_buckets = CONFIG["quantile_buckets"] if n_buckets is None else n_buckets
    # Resolved ONCE here and reused for both the actual computation and the
    # result metadata below — fixes a bug where execution_lag_bars=0 was
    # silently replaced by the CONFIG default in the metadata dict (an
    # `x or default` pattern treats 0 as falsy) even though the actual
    # signal alignment already used 0 correctly. See Section Z changelog.
    resolved_execution_lag = CONFIG["execution"]["execution_lag_bars"] if execution_lag_bars is None else execution_lag_bars
    resolved_execution_price = CONFIG["execution"]["execution_price"] if execution_price is None else execution_price
    if resolved_execution_price not in ("close", "open"):
        raise ValueError(f"execution_price must be 'close' or 'open', got {resolved_execution_price!r}")

    if holding_period < 1:
        raise ValueError("holding_period must be >= 1")
    if portfolio not in PORTFOLIO_TYPES:
        raise ValueError(f"portfolio must be one of {PORTFOLIO_TYPES}")
    if weighting not in WEIGHTING_SCHEMES:
        raise ValueError(f"weighting must be one of {WEIGHTING_SCHEMES}")

    tickers = get_universe_tickers(universe)
    if ohlcv is None:
        ohlcv = get_ohlcv(tickers)
    close_full = ohlcv["close"]

    if universe_mask_and_meta is None:
        mask_full, universe_meta = get_universe(universe, close_full, market_cap=market_cap)
    else:
        mask_full, universe_meta = universe_mask_and_meta

    if fields is None:
        features = compute_features(ohlcv)
        fields_full = dict(features)
        fields_full.update(ohlcv)
        fields_full = register_external_scores(fields_full, close_full.index, tickers)
    else:
        fields_full = fields

    alpha_full = evaluate_expression(expression, fields_full, mask_full, group_map)
    alpha_actionable_full = align_signal_to_execution(alpha_full, resolved_execution_lag)
    execution_price_full = get_execution_price(ohlcv, resolved_execution_price)

    if start not in close_full.index and pd.Timestamp(start) < close_full.index.min():
        raise ValueError(f"Requested start {start} is before available data ({close_full.index.min().date()}).")

    alpha_actionable = alpha_actionable_full.loc[start:end]
    execution_price_ = execution_price_full.loc[start:end]
    mask = mask_full.loc[start:end]
    close = close_full.loc[start:end]

    if alpha_actionable.empty:
        raise ValueError(f"No data in requested window {start}..{end} for universe {universe}.")
    if (mask.sum(axis=1) == 0).all():
        raise ValueError(f"Universe {universe} has zero coverage across the entire window {start}..{end}.")
    # P0 (V2 finalize pass): an expression that references a longer lookback
    # than the available history before `start` (e.g. sma_200 on a 30-day
    # window) rolls out to all-NaN rather than crashing -- but silently
    # returning a BacktestResult full of NaN metrics looks exactly like a
    # legitimate "this strategy has ~0 Sharpe" result, which is a misleading
    # partial result, not an explicit failure. Fail loudly instead.
    if alpha_actionable.notna().sum().sum() == 0:
        raise ValueError(
            f"Alpha expression '{expression}' produced no valid (non-NaN) values anywhere in "
            f"{start}..{end} for universe {universe} -- this almost always means insufficient "
            f"history before `start` for the expression's lookback window(s). Request more "
            f"history (push `start` later or fetch data from further back) or shorten the "
            f"expression's lookback."
        )

    bt = run_staggered_backtest(
        alpha_actionable, execution_price_, holding_period, portfolio, weighting,
        transaction_cost_bps, slippage_bps, n_buckets=n_buckets, k=k,
        max_position_weight=max_position_weight, long_exposure=long_exposure, short_exposure=short_exposure,
    )

    fwd_returns = compute_forward_returns(execution_price_, holding_period).where(mask)
    ic_series = compute_daily_ic(alpha_actionable, fwd_returns)
    icd = ic_diagnostics(ic_series)

    cum_gross = (1 + bt["gross_returns"].fillna(0)).cumprod()
    cum_net = (1 + bt["net_returns"].fillna(0)).cumprod()
    ddstats = drawdown_stats(cum_net)

    exposures = exposure_series(bt["weights"])
    qsummary = quantile_analysis(alpha_actionable, fwd_returns, n_buckets=10)

    # Explicit benchmark injection supports deterministic/offline validation.
    # Production calls omit it and use the configured benchmark data provider.
    bench_price = fetch_benchmark(universe, close.index) if benchmark_price is None else benchmark_price.reindex(close.index)
    bench = benchmark_analysis(bt["net_returns"], bench_price)

    fields_window = {k_: (v.loc[start:end] if isinstance(v, pd.DataFrame) else v) for k_, v in fields_full.items()}
    factor_exp = factor_exposure_analysis(bt["net_returns"], fields_window, mask)

    coverage = coverage_diagnostics(alpha_actionable)

    ann_factor = 252 / holding_period
    ann_return_gross = annualize_return(bt["gross_returns"], 252)
    ann_return_net = annualize_return(bt["net_returns"], 252)
    ann_vol = annualize_vol(bt["net_returns"], 252)

    result = BacktestResult(
        expression=expression, universe=universe, universe_metadata=universe_meta,
        start_date=start, end_date=end, holding_period=holding_period,
        execution_config={"execution_lag_bars": resolved_execution_lag,
                           "execution_price": resolved_execution_price},
        portfolio_type=portfolio, weighting=weighting,
        cost_assumptions={"transaction_cost_bps": transaction_cost_bps, "slippage_bps": slippage_bps},

        ic_mean=icd["ic_mean"], ic_std=icd["ic_std"], ic_ir=icd["ic_ir"], pct_positive_ic=icd["pct_positive"],
        sharpe_gross=sharpe_ratio(bt["gross_returns"]), sharpe_net=sharpe_ratio(bt["net_returns"]),
        sortino=sortino_ratio(bt["net_returns"]),
        calmar=calmar_ratio(ann_return_net, ddstats["max_drawdown"]),
        annual_return_gross=ann_return_gross, annual_return_net=ann_return_net, annual_vol=ann_vol,
        max_drawdown=ddstats["max_drawdown"], drawdown_duration_days=ddstats["drawdown_duration_days"],
        win_rate=win_rate(bt["net_returns"]), profit_factor=profit_factor(bt["net_returns"]),
        # turnover_series is already a DAILY portfolio turnover series — the
        # staggered/cohort construction already accounts for the holding
        # period (only ~1/holding_period of the book rotates on any given
        # day), so annualizing must NOT divide by holding_period a second
        # time. Previously did `turnover.mean() * (252/holding_period)`,
        # which double-counted the holding-period effect and understated
        # turnover for hp>1. Fixed to `turnover.mean() * 252`.
        turnover_mean=float(bt["turnover"].mean()), turnover_annual=float(bt["turnover"].mean() * 252),

        long_exposure_mean=float(exposures["long_exposure"].mean()),
        short_exposure_mean=float(exposures["short_exposure"].mean()),
        gross_exposure_mean=float(exposures["gross_exposure"].mean()),
        net_exposure_mean=float(exposures["net_exposure"].mean()),

        benchmark=bench, factor_exposures=factor_exp,
        coverage={"avg_coverage": coverage["avg_coverage"], "min_coverage": coverage["min_coverage"]},
        survivorship_bias_risk=universe_meta["survivorship_bias_risk"],

        ic_series=ic_series, gross_returns=bt["gross_returns"], net_returns=bt["net_returns"],
        cum_gross_returns=cum_gross, cum_net_returns=cum_net, turnover_series=bt["turnover"],
        drawdown_series=ddstats["drawdown_series"], exposures=exposures, quantile_summary=qsummary,

        metadata={
            "run_at": str(datetime.now()), "data_version": _DATA_VERSION,
            "pandas_version": pd.__version__, "numpy_version": np.__version__,
            "n_experiments_this_session": TRACKER.count() + 1,
            # which registered external fields the expression actually references,
            # plus their reproducibility info (source file, availability column,
            # date range) — Section 12. Simple substring match against the
            # expression string; good enough for a notebook experiment record,
            # not meant to be a full dependency parser.
            "external_fields_used": {
                name: meta for name, meta in EXTERNAL_FIELD_METADATA.items() if name in expression
            },
        },
    )

    if not _skip_tracker:
        TRACKER.record(expression, {"universe": universe, "holding_period": holding_period,
                                     "portfolio": portfolio, "weighting": weighting,
                                     "transaction_cost_bps": transaction_cost_bps})
        TRACKER.warn_if_needed()

    return result


def print_backtest_summary(result: BacktestResult):
    print(f"--- {result.expression}  |  {result.universe}  {result.start_date}..{result.end_date} "
          f"  hp={result.holding_period}  {result.portfolio_type}/{result.weighting} ---")
    for k_, v in result.summary().items():
        print(f"  {k_:>22}: {v:.4f}" if isinstance(v, float) else f"  {k_:>22}: {v}")
    if result.survivorship_bias_risk:
        print("  [!] survivorship_bias_risk = True — see universe_metadata['notes']")


# --- Exported from notebook cell 41 ---


def sensitivity_analysis(expression: str, universe: str, start: str, end: str, **base_kwargs) -> dict:
    """Runs the fixed expression across period / universe / holding-period /
    cost / portfolio-construction variations. Returns a dict of DataFrames,
    one per axis, plus a stability note (std of Sharpe across each axis —
    high std = the result is fragile to that choice, not proof either way)."""
    results = {}

    # -- year-by-year --
    years = pd.date_range(start, end, freq="YS").year.tolist()
    rows = []
    for y in years:
        y_start, y_end = f"{y}-01-01", f"{y}-12-31"
        try:
            r = run_backtest(expression, universe, y_start, y_end, _skip_tracker=True, **base_kwargs)
            rows.append({"year": y, "sharpe_net": r.sharpe_net, "ic_mean": r.ic_mean, "turnover_annual": r.turnover_annual})
        except Exception as e:
            rows.append({"year": y, "error": str(e)})
    results["by_year"] = pd.DataFrame(rows)

    # -- holding period --
    rows = []
    for hp in (1, 3, 5, 10, 20):
        try:
            r = run_backtest(expression, universe, start, end, holding_period=hp, _skip_tracker=True, **base_kwargs)
            rows.append({"holding_period": hp, "sharpe_net": r.sharpe_net, "ic_mean": r.ic_mean, "turnover_annual": r.turnover_annual})
        except Exception as e:
            rows.append({"holding_period": hp, "error": str(e)})
    results["by_holding_period"] = pd.DataFrame(rows)

    # -- costs --
    rows = []
    for bps in (0, 5, 10, 20):
        try:
            r = run_backtest(expression, universe, start, end, transaction_cost_bps=bps, slippage_bps=0,
                              _skip_tracker=True, **base_kwargs)
            rows.append({"cost_bps": bps, "sharpe_net": r.sharpe_net, "annual_return_net": r.annual_return_net})
        except Exception as e:
            rows.append({"cost_bps": bps, "error": str(e)})
    results["by_cost"] = pd.DataFrame(rows)

    # -- portfolio construction --
    rows = []
    for port, weight in [("LONG_SHORT", "EQUAL_WEIGHT"), ("LONG_SHORT", "SIGNAL_WEIGHTED"),
                          ("LONG_ONLY", "EQUAL_WEIGHT"), ("LONG_ONLY", "SIGNAL_WEIGHTED")]:
        try:
            r = run_backtest(expression, universe, start, end, portfolio=port, weighting=weight,
                              _skip_tracker=True, **base_kwargs)
            rows.append({"portfolio": port, "weighting": weight, "sharpe_net": r.sharpe_net})
        except Exception as e:
            rows.append({"portfolio": port, "weighting": weight, "error": str(e)})
    results["by_construction"] = pd.DataFrame(rows)

    sharpe_values = []
    for df in results.values():
        if "sharpe_net" in df.columns:
            sharpe_values.extend(df["sharpe_net"].dropna().tolist())
    results["stability_note"] = (
        f"Sharpe across all {len(sharpe_values)} sensitivity runs: "
        f"mean={np.mean(sharpe_values):.2f}, std={np.std(sharpe_values):.2f}. "
        f"High std relative to mean suggests the result is fragile to these choices."
    ) if sharpe_values else "No successful runs to summarize."

    return results


def parameter_sensitivity(expression_template: str, param_grid: dict, universe: str, start: str, end: str,
                           **base_kwargs) -> pd.DataFrame:
    """expression_template e.g. 'rank(ts_zscore(momentum_{m}, {z}))' with
    param_grid = {'m': [5, 20, 60], 'z': [10, 20, 30]}. Produces one row per
    combination — look for stable *regions*, not an isolated peak (Section 29)."""
    keys = list(param_grid.keys())
    rows = []
    for combo in itertools.product(*param_grid.values()):
        params = dict(zip(keys, combo))
        expr = expression_template.format(**params)
        try:
            r = run_backtest(expr, universe, start, end, _skip_tracker=True, **base_kwargs)
            rows.append({**params, "expression": expr, "sharpe_net": r.sharpe_net, "ic_mean": r.ic_mean})
        except Exception as e:
            rows.append({**params, "expression": expr, "error": str(e)})
    return pd.DataFrame(rows)


# --- Exported from notebook cell 43 ---


def compare_alphas(alpha_dict: dict, close: pd.DataFrame, universe_mask: pd.DataFrame,
                    holding_period: int = 1) -> dict:
    names = list(alpha_dict.keys())
    signal_corr = pd.DataFrame(index=names, columns=names, dtype=float)
    return_series = {}
    for name, alpha in alpha_dict.items():
        weights = alpha.apply(lambda row: construct_portfolio_row(row, "LONG_SHORT", "EQUAL_WEIGHT"), axis=1)
        asset_returns = close.pct_change()
        return_series[name] = (weights.shift(1).fillna(0.0) * asset_returns).sum(axis=1)

    for a in names:
        for b in names:
            corrs = []
            for d in alpha_dict[a].index:
                if d not in alpha_dict[b].index:
                    continue
                both = pd.concat([alpha_dict[a].loc[d], alpha_dict[b].loc[d]], axis=1).dropna()
                if len(both) >= 5:
                    corrs.append(both.iloc[:, 0].corr(both.iloc[:, 1]))
            signal_corr.loc[a, b] = np.nanmean(corrs) if corrs else np.nan

    return_corr = pd.DataFrame(return_series).corr()
    return {"signal_correlation": signal_corr, "return_correlation": return_corr}


# --- Exported interface contract ---

UNVERIFIED_OPERATOR_SEMANTICS = {
    "kth_element": "Assumed meaning: k-th most recent value in a trailing window of length d "
                    "(1-indexed from most recent). No authoritative spec was supplied to verify this "
                    "against any external platform\'s operator of the same name.",
    "last_diff_value": "Assumed meaning: the most recent value in x that differs from the current "
                        "value, searched backward up to d bars. Unverified against an external spec.",
    "ts_scale": "Assumed meaning: min-max rescale x into [0, 1] over a trailing window of length d "
                "((x - ts_min)/(ts_max - ts_min)). Unverified against an external spec.",
    "densify": "Assumed meaning: cross-sectional dense-rank remapped to consecutive integers "
               "starting at 0, dropping gaps left by NaN/out-of-universe entries. Unverified against "
               "an external spec.",
}
VERIFIED_OPERATOR_SEMANTICS = {
    "group_scale": "Verified: group-wise min-max scale (x - group_min) / (group_max - group_min); "
                    "single-member/constant groups and zero denominators yield NaN, not a crash.",
    "group_backfill": "Verified: fills with the trailing-d-day winsorized MEAN of the ticker\'s own "
                       "group (NaNs ignored, winsorized at the supplied std before averaging).",
    "group_mean": "Verified: arithmetic mean of all tickers in the same group on the same date.",
    "hump": "Verified: dampens by exactly `allowed_change` toward the new value when the move exceeds "
            "the threshold (output = prev + sign(change)*allowed_change), not a jump to the full new value.",
    "ts_backfill": "Verified: ts_backfill(x, d, k=1) fills with the k-th most recent valid value in "
                    "the trailing d-bar window; k=1 (default) matches the original no-k-arg behavior.",
}

def describe_interface() -> dict:
    """The single frozen, machine-readable description of what this engine
    supports (P2). Built live off the actual registries used at runtime, so
    it cannot describe an operator/universe/portfolio-type that doesn\'t
    really exist, or omit one that does."""
    engineered_fields = ["momentum_5", "momentum_20", "momentum_60",
                          "volatility_5", "volatility_20", "volatility_60",
                          "rsi_7", "rsi_14", "atr_14",
                          "sma_20", "sma_50", "sma_200",
                          "ema_9", "ema_20", "ema_50", "macd",
                          "volume_ratio_20", "volume_ratio_60"]
    native_ohlcv_fields = ["open", "high", "low", "close", "volume"]
    return {
        "operators": {
            "elementwise_and_timeseries": sorted(OPERATORS.keys()),
            "group_aware": sorted(GROUP_OPERATORS.keys()),
            "unverified_semantics": UNVERIFIED_OPERATOR_SEMANTICS,
            "verified_semantics": VERIFIED_OPERATOR_SEMANTICS,
        },
        "fields": {
            "native_ohlcv": native_ohlcv_fields,
            "engineered": engineered_fields,
            "external": "any CSV dropped into CONFIG[\'external_scores_dir\'] is auto-registered under "
                        "its filename (minus .csv) as an additional field -- see format below.",
        },
        "expression_syntax": "A single Python expression string, parsed as an AST (not eval()\'d "
                              "directly). Allowed: field names, operator calls (name(args...)), "
                              "arithmetic (+ - * / **), comparisons, unary minus, list/tuple literals, "
                              "numeric/string constants. Anything else (imports, attribute access, "
                              "comprehensions, lambdas, etc.) raises AlphaExpressionError.",
        "universes": {
            "NIFTY50": "Only enabled universe. Static constituent list; survivorship_bias_risk=True, "
                       "point_in_time=False."
        },
        "external_score_csv_format": {
            "required_columns": ["ticker", "value"],
            "date_column": "\'available_date\' (preferred, used for alignment when present) or "
                           "\'date\'. An \'event_date\' column alone is rejected -- it doesn\'t say "
                           "when the score was actually knowable, so it would risk look-ahead.",
            "validation": "empty/NaN tickers, unparseable dates, non-numeric values, and duplicate "
                          "ticker/date rows (resolved deterministically, last-row-wins) are all "
                          "explicitly validated -- malformed files raise ValueError, never silently load.",
        },
        "portfolio_types": sorted(PORTFOLIO_TYPES),
        "weighting_schemes": sorted(WEIGHTING_SCHEMES),
        "execution_settings": {"execution_lag_bars": "int >= 0", "execution_price": "\'close\' or \'open\'"},
    }


# --- Exported request/result API contract ---

import uuid
import math
import inspect

_API_ALLOWED_FIELDS = {
    "expression", "universe", "start", "end", "holding_period", "portfolio",
    "weighting", "transaction_cost_bps", "slippage_bps", "execution_lag_bars",
    "execution_price", "n_buckets", "k", "max_position_weight",
    "long_exposure", "short_exposure", "group_map",
}
_API_UNIVERSES = {"NIFTY50"}

def _require_finite_number(req: dict, key: str, min_val=None, max_val=None,
                           min_inclusive=True, max_inclusive=True, require_int=False):
    if key not in req or req[key] is None:
        return
    v = req[key]
    if isinstance(v, bool) or not isinstance(v, (int, float, np.integer, np.floating)):
        raise ValueError(f"'{key}' must be a number, got {type(v).__name__}")
    if not np.isfinite(v):
        raise ValueError(f"'{key}' must be finite")
    if require_int:
        if int(v) != v:
            raise ValueError(f"'{key}' must be an integer, got {v!r}")
        req[key] = int(v)  # normalize 2.0 to 2 before runtime
        v = req[key]
    else:
        req[key] = float(v)
        v = req[key]
    if min_val is not None:
        ok = v >= min_val if min_inclusive else v > min_val
        if not ok:
            op = ">=" if min_inclusive else ">"
            raise ValueError(f"'{key}' must be {op} {min_val}, got {v!r}")
    if max_val is not None:
        ok = v <= max_val if max_inclusive else v < max_val
        if not ok:
            op = "<=" if max_inclusive else "<"
            raise ValueError(f"'{key}' must be {op} {max_val}, got {v!r}")

def _normalize_api_date(value, field):
    if not isinstance(value, (str, pd.Timestamp, datetime, np.datetime64)):
        raise ValueError(f"'{field}' must be an ISO date string or datetime, got {type(value).__name__}")
    try:
        ts = pd.Timestamp(value)
    except Exception as exc:
        raise ValueError(f"'{field}' is not a parseable date: {exc}") from exc
    if pd.isna(ts):
        raise ValueError(f"'{field}' must not be NaT/NaN")
    if ts.tz is not None:
        raise ValueError(f"'{field}' must be timezone-naive; send dates in the market-data timezone")
    # Preserve date-only semantics while normalizing datetime values.
    if isinstance(value, str) and len(value.strip()) == 10 and ts == ts.normalize():
        return ts.strftime("%Y-%m-%d"), ts
    return ts.isoformat(), ts

def validate_backtest_request(request: dict) -> dict:
    """Validate and normalize the public API request. Raises ValueError only."""
    if not isinstance(request, dict):
        raise ValueError(f"request must be a dict, got {type(request).__name__}")
    req = dict(request)
    if any(not isinstance(key, str) for key in req):
        raise ValueError("all request field names must be strings")

    unknown = sorted(set(req) - _API_ALLOWED_FIELDS)
    if unknown:
        raise ValueError(f"unknown request field(s): {', '.join(map(str, unknown))}")
    for key in ("expression", "universe", "start", "end"):
        if key not in req or req[key] is None or req[key] == "":
            raise ValueError(f"request is missing required field '{key}'")

    if not isinstance(req["expression"], str) or not req["expression"].strip():
        raise ValueError("'expression' must be a non-empty string")
    req["expression"] = req["expression"].strip()

    if not isinstance(req["universe"], str):
        raise ValueError("'universe' must be a string")
    req["universe"] = req["universe"].strip().upper()
    if req["universe"] not in _API_UNIVERSES:
        raise ValueError("Only NIFTY50 is enabled in this build. Select NIFTY50.")

    for key, choices in (
        ("portfolio", PORTFOLIO_TYPES),
        ("weighting", WEIGHTING_SCHEMES),
        ("execution_price", ("close", "open")),
    ):
        if key in req and req[key] is not None:
            if not isinstance(req[key], str) or req[key] not in choices:
                raise ValueError(f"'{key}' must be one of {sorted(choices)}, got {req[key]!r}")

    start_text, start_ts = _normalize_api_date(req["start"], "start")
    end_text, end_ts = _normalize_api_date(req["end"], "end")
    if start_ts > end_ts:
        raise ValueError("'start' must not be after 'end'")
    req["start"], req["end"] = start_text, end_text

    _require_finite_number(req, "holding_period", min_val=1, require_int=True)
    _require_finite_number(req, "n_buckets", min_val=2, require_int=True)
    _require_finite_number(req, "k", min_val=1, require_int=True)
    _require_finite_number(req, "execution_lag_bars", min_val=0, require_int=True)
    _require_finite_number(req, "transaction_cost_bps", min_val=0)
    _require_finite_number(req, "slippage_bps", min_val=0)
    _require_finite_number(req, "long_exposure", min_val=0)
    _require_finite_number(req, "short_exposure", min_val=0)
    _require_finite_number(req, "max_position_weight", min_val=0, min_inclusive=False, max_val=1)

    if "group_map" in req and req["group_map"] is not None:
        gm = req["group_map"]
        if not isinstance(gm, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in gm.items()):
            raise ValueError("'group_map' must be a dictionary mapping ticker strings to group strings")

    return req

def _json_safe(value):
    """Safe serializer for API echoes/errors; never leaks arbitrary objects."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (float, np.floating)):
        x = float(value)
        return x if np.isfinite(x) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (pd.Timestamp, datetime, np.datetime64)):
        try:
            ts = pd.Timestamp(value)
            return None if pd.isna(ts) else ts.isoformat()
        except Exception:
            return repr(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    return repr(value)

def run_backtest_api(request, _ohlcv=None, _fields=None, _universe_mask_and_meta=None,
                     _benchmark_price=None) -> dict:
    """In-process request boundary returning a strict JSON-safe envelope.

    This is not an HTTP server. The production web service must add authentication,
    authorization, rate limits, job execution, durable shared storage, observability,
    and deployment configuration around this callable.
    """
    experiment_id = f"exp-{uuid.uuid4().hex}"
    if not isinstance(request, dict):
        err = ValueError(f"request must be a dict, got {type(request).__name__}")
        TRACKER.record_failure("<invalid>", {"_raw_request_type": type(request).__name__},
                               err, experiment_id=experiment_id)
        return {"experiment_id": experiment_id, "status": "error",
                "error": {"type": "ValidationError", "message": str(err)},
                "config": _json_safe(request), "result": None}

    try:
        validated = validate_backtest_request(request)
    except Exception as exc:
        # Treat all failures at the input boundary as validation failures.
        err = ValueError(str(exc))
        TRACKER.record_failure(str(request.get("expression", "<invalid>")),
                               _json_safe(request), err, experiment_id=experiment_id)
        return {"experiment_id": experiment_id, "status": "error",
                "error": {"type": "ValidationError", "message": str(err)},
                "config": _json_safe(request), "result": None}

    run_kwargs = dict(validated)
    for key in ("expression", "universe", "start", "end"):
        run_kwargs.pop(key, None)
    try:
        result = run_backtest(
            validated["expression"], validated["universe"],
            validated["start"], validated["end"],
            ohlcv=_ohlcv, fields=_fields,
            universe_mask_and_meta=_universe_mask_and_meta,
            benchmark_price=_benchmark_price,
            _skip_tracker=True, **run_kwargs
        )
        result_payload = result.to_dict()
        # Enforce the wire contract now, not later in the HTTP layer.
        json.dumps(result_payload, allow_nan=False)
    except Exception as exc:
        TRACKER.record_failure(validated["expression"], validated, exc, experiment_id=experiment_id)
        return {"experiment_id": experiment_id, "status": "error",
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "config": _json_safe(validated), "result": None}

    TRACKER.record(validated["expression"], validated, status="success",
                   result_summary=_json_safe(result.summary().to_dict()),
                   experiment_id=experiment_id)
    TRACKER.warn_if_needed()
    response = {"experiment_id": experiment_id, "status": "success", "error": None,
                "config": _json_safe(validated), "result": result_payload}
    # A final invariant: the full envelope must be serializable without fallback.
    json.dumps(response, allow_nan=False)
    return response
