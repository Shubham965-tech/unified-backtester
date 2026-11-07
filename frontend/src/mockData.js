export const demoExamples = [
  { name: "Momentum z-score", expression: "rank(ts_zscore(momentum_20, 20))", category: "Momentum" },
  { name: "Short-term reversal", expression: "-rank(momentum_5)", category: "Reversal" },
  { name: "Sector-neutral momentum", expression: "group_neutralize(rank(momentum_20 / volatility_20))", category: "Neutralized" },
  { name: "Volume surge", expression: "rank(ts_zscore(volume_ratio_20, 20)) * sign(momentum_5)", category: "Volume" },
  { name: "RSI mean reversion", expression: "-rank(rsi_14)", category: "Mean reversion" },
  { name: "Trend vs 50d average", expression: "rank(close / sma_50 - 1)", category: "Trend" }
];

const seeded = (seed) => {
  let x = seed >>> 0;
  return () => { x = (1664525 * x + 1013904223) >>> 0; return x / 4294967296; };
};

export function makeDemoResult(expression = "rank(ts_zscore(momentum_20, 20))", settings = {}) {
  const rand = seeded(expression.length * 313 + (settings.universe || "NIFTY50").length * 71);
  const dates = [];
  const cumNet = [], cumGross = [], drawdown = [], rollingSharpe = [], turnover = [], icValues = [], long = [], short = [], net = [];
  let gross = 1, afterCosts = 1, peak = 1;
  for (let i = 0; i < 96; i++) {
    const year = 2018 + Math.floor(i / 12);
    const month = i % 12;
    dates.push(`${year}-${String(month + 1).padStart(2, "0")}-01`);
    const ret = 0.009 + (rand() - 0.52) * 0.075;
    const cost = 0.0015 + rand() * 0.002;
    gross *= 1 + ret;
    afterCosts *= 1 + ret - cost;
    peak = Math.max(peak, afterCosts);
    cumGross.push(Number((gross - 1).toFixed(4)));
    cumNet.push(Number((afterCosts - 1).toFixed(4)));
    drawdown.push(Number((afterCosts / peak - 1).toFixed(4)));
    rollingSharpe.push(Number((0.65 + rand() * 1.35).toFixed(3)));
    turnover.push(Number((0.08 + rand() * 0.22).toFixed(3)));
    icValues.push(Number(((rand() - 0.42) * 0.12).toFixed(4)));
    long.push(Number((0.45 + rand() * 0.2).toFixed(3)));
    short.push(Number((-0.45 - rand() * 0.2).toFixed(3)));
    net.push(Number((long[i] + short[i]).toFixed(3)));
  }
  const yearly = Array.from({ length: 8 }, (_, i) => {
    const y = 2018 + i;
    return { year: y, return: Number((-2 + rand() * 24).toFixed(1)), sharpe: Number((0.45 + rand() * 1.3).toFixed(2)), volatility: Number((12 + rand() * 9).toFixed(1)), maxDD: Number((-7 - rand() * 17).toFixed(1)), turnover: Number((2.5 + rand() * 2.5).toFixed(1)), ic: Number((0.015 + rand() * 0.06).toFixed(3)), days: 245 };
  });
  const quantiles = Array.from({ length: 10 }, (_, i) => ({ bucket: i + 1, avg_return: Number((-0.0035 + i * 0.00085 + (rand() - .5) * .0008).toFixed(5)), cumulative_return: Number((-0.15 + i * 0.084 + (rand() - .5) * 0.05).toFixed(3)) }));
  return {
    experiment_id: `demo-${Math.random().toString(16).slice(2, 8)}`,
    status: "success", elapsed_s: 7.8, data_mode: "synthetic",
    config: { expression, universe: settings.universe || "NIFTY50", start: settings.start || "2018-01-01", end: settings.end || "2025-12-31", holding_period: Number(settings.holding_period || 1), portfolio: settings.portfolio || "LONG_SHORT", weighting: settings.weighting || "EQUAL_WEIGHT" },
    summary: { annual_return_net: 0.126, annual_return_gross: 0.158, sharpe_net: 1.42, sharpe_gross: 1.71, sortino: 2.11, calmar: 0.86, max_drawdown: -0.148, turnover_annual: 4.3, ic_mean: 0.045, ic_ir: 0.62, fitness: 1.32, coverage_avg: 0.94, win_rate: 0.56, profit_factor: 1.48 },
    benchmark: { available: true, label: "NIFTY50", annual_return: 0.082, beta: 0.84, correlation: 0.76 },
    warnings: ["DEMO DATA — illustrative metrics only; not market evidence.", "Synthetic universe membership does not model survivorship or point-in-time changes."],
    universe: { name: settings.universe || "NIFTY50", construction: "Synthetic preset", point_in_time: false, survivorship_bias_risk: true, n_assets: 50 },
    series: { dates, cum_gross: cumGross, cum_net: cumNet, drawdown, rolling_sharpe: rollingSharpe, turnover, long, short, net },
    ic: { dates, values: icValues, rolling: icValues.map((v, i) => Number((icValues.slice(Math.max(0, i - 5), i + 1).reduce((a,b)=>a+b,0) / (Math.min(i + 1, 6))).toFixed(4))) },
    quantiles, yearly
  };
}

export function demoAlphas() {
  return [
    { id: "AL-1042", name: "Momentum z-score", expression: demoExamples[0].expression, status: "Ready", universe: "NIFTY50", sharpe: 1.42, ret: 12.6, turnover: 4.3, ic: .045, updated: "Today, 09:42", tags: ["momentum", "baseline"] },
    { id: "AL-1039", name: "Sector-neutral momentum", expression: demoExamples[2].expression, status: "Ready", universe: "NIFTY50", sharpe: 1.18, ret: 9.8, turnover: 3.7, ic: .038, updated: "Yesterday", tags: ["neutralized"] },
    { id: "AL-1035", name: "Short-term reversal", expression: demoExamples[1].expression, status: "Warning", universe: "NIFTY50", sharpe: .83, ret: 5.2, turnover: 7.1, ic: .021, updated: "Oct 15", tags: ["reversal"] },
    { id: "AL-1028", name: "Volume surge", expression: demoExamples[3].expression, status: "Running", universe: "NIFTY50", sharpe: null, ret: null, turnover: null, ic: null, updated: "Oct 14", tags: ["volume"] },
    { id: "AL-1022", name: "RSI mean reversion", expression: demoExamples[4].expression, status: "Failed", universe: "NIFTY50", sharpe: null, ret: null, turnover: null, ic: null, updated: "Oct 11", tags: ["mean-reversion"] }
  ];
}
