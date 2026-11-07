"""Regression tests for alpha sign symmetry and portfolio weighting."""
import numpy as np
import pandas as pd

from alpha_engine import construct_portfolio_row, sharpe_ratio, compute_daily_ic


def test_negated_alpha_reverses_symmetric_long_short_weights():
    alpha = pd.Series([0.2, 0.5, 0.9, -0.1, -0.4, -0.8],
                      index=list("ABCDEF"))
    for weighting in ("EQUAL_WEIGHT", "SIGNAL_WEIGHTED", "RANK_WEIGHTED", "NORMALIZED_SIGNAL"):
        w = construct_portfolio_row(alpha, "LONG_SHORT", weighting, n_buckets=3)
        w_neg = construct_portfolio_row(-alpha, "LONG_SHORT", weighting, n_buckets=3)
        np.testing.assert_allclose(w_neg.values, -w.values, atol=1e-12,
                                   err_msg=f"sign symmetry failed for {weighting}")


def test_negated_alpha_reverses_top_bottom_weights():
    alpha = pd.Series([0.2, 0.5, 0.9, -0.1, -0.4, -0.8], index=list("ABCDEF"))
    for weighting in ("EQUAL_WEIGHT", "SIGNAL_WEIGHTED", "RANK_WEIGHTED", "NORMALIZED_SIGNAL"):
        w = construct_portfolio_row(alpha, "TOP_BOTTOM", weighting, k=2)
        w_neg = construct_portfolio_row(-alpha, "TOP_BOTTOM", weighting, k=2)
        np.testing.assert_allclose(w_neg.values, -w.values, atol=1e-12,
                                   err_msg=f"sign symmetry failed for TOP_BOTTOM/{weighting}")


def test_negated_returns_flip_gross_sharpe():
    returns = pd.Series([0.01, -0.004, 0.006, -0.002, 0.008, -0.003])
    assert np.isclose(sharpe_ratio(-returns), -sharpe_ratio(returns))


def test_unary_minus_is_supported_by_expression_parser():
    # A tiny field matrix verifies the AST interpreter accepts unary minus.
    from alpha_engine import evaluate_expression
    idx, cols = pd.date_range("2024-01-01", periods=3), list("ABCDE")
    frame = pd.DataFrame(np.arange(15, dtype=float).reshape(3, 5), index=idx, columns=cols)
    positive = evaluate_expression("close", {"close": frame})
    negative = evaluate_expression("-close", {"close": frame})
    pd.testing.assert_frame_equal(negative, -positive)


def test_ranked_expression_negation_reverses_long_short_weights():
    from alpha_engine import evaluate_expression
    idx = pd.date_range("2024-01-01", periods=4)
    cols = list("ABCDEF")
    raw = pd.DataFrame(
        [[1, 2, 2, 4, 5, 6], [6, 5, 4, 3, 2, 1],
         [1, 1, 2, 3, 3, 4], [4, 3, 3, 2, 1, 1]],
        index=idx, columns=cols, dtype=float,
    )
    a = evaluate_expression("rank(close)", {"close": raw})
    a_neg = evaluate_expression("-rank(close)", {"close": raw})
    for date in idx:
        w = construct_portfolio_row(a.loc[date], "LONG_SHORT", "EQUAL_WEIGHT", n_buckets=3)
        w_neg = construct_portfolio_row(a_neg.loc[date], "LONG_SHORT", "EQUAL_WEIGHT", n_buckets=3)
        np.testing.assert_allclose(w_neg.values, -w.values, atol=1e-12)


def test_full_gross_backtest_is_sign_symmetric_for_ranked_alpha():
    from alpha_engine import evaluate_expression, run_staggered_backtest
    idx = pd.date_range("2024-01-01", periods=40)
    cols = list("ABCDEF")
    rng = np.random.default_rng(7)
    close = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0005, 0.01, size=(40, 6)), axis=0),
        index=idx, columns=cols,
    )
    alpha = evaluate_expression("rank(close)", {"close": close})
    alpha_neg = evaluate_expression("-rank(close)", {"close": close})
    prices = close
    kwargs = dict(holding_period=1, portfolio_type="LONG_SHORT", weighting="EQUAL_WEIGHT",
                  transaction_cost_bps=0.0, slippage_bps=0.0, n_buckets=3)
    result = run_staggered_backtest(alpha, prices, **kwargs)
    result_neg = run_staggered_backtest(alpha_neg, prices, **kwargs)
    np.testing.assert_allclose(result_neg["weights"].values, -result["weights"].values, atol=1e-12)
    np.testing.assert_allclose(result_neg["gross_returns"].values, -result["gross_returns"].values, atol=1e-12)
    assert np.isclose(sharpe_ratio(result_neg["gross_returns"]), -sharpe_ratio(result["gross_returns"]))


def test_tied_alpha_sign_symmetry_across_symmetric_portfolios_and_weightings():
    alpha = pd.Series([0.2, 0.2, 0.4, 0.4, 0.8, 0.8], index=list("ABCDEF"))
    for portfolio, kwargs in (("LONG_SHORT", {"n_buckets": 3}), ("TOP_BOTTOM", {"k": 2})):
        for weighting in ("EQUAL_WEIGHT", "SIGNAL_WEIGHTED", "RANK_WEIGHTED", "NORMALIZED_SIGNAL"):
            w = construct_portfolio_row(alpha, portfolio, weighting, **kwargs)
            w_neg = construct_portfolio_row(-alpha, portfolio, weighting, **kwargs)
            np.testing.assert_allclose(
                w_neg.values, -w.values, atol=1e-12,
                err_msg=f"tie sign symmetry failed for {portfolio}/{weighting}",
            )


def test_only_nifty50_is_advertised_and_accepted():
    from alpha_engine import describe_interface, validate_backtest_request
    assert list(describe_interface()["universes"].keys()) == ["NIFTY50"]
    base = {"expression": "rank(close)", "universe": "NIFTY50",
            "start": "2024-01-01", "end": "2024-12-31"}
    assert validate_backtest_request(base)["universe"] == "NIFTY50"
    for disabled in ("NIFTY100", "TOP250", "TOP500", "CUSTOM"):
        bad = {**base, "universe": disabled}
        try:
            validate_backtest_request(bad)
        except ValueError as exc:
            assert "Only NIFTY50" in str(exc)
        else:
            raise AssertionError(f"{disabled} should be disabled")
