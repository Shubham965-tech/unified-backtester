import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, BarChart3, Bell, BookOpen,
  Check, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Clock3,
  Code2, Command, Copy, Database, Download, FileClock, FileJson, Filter, FlaskConical,
  FolderOpen, Gauge, GitCompare, History, Layers3, LayoutDashboard, ListFilter, Menu,
  MoreHorizontal, PanelLeftClose, Play, Plus, RefreshCw, Search, Settings2, ShieldCheck,
  SlidersHorizontal, Sparkles, Terminal, TrendingDown, TrendingUp, X, Zap
} from "lucide-react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line,
  LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis
} from "recharts";
import { getExamples, getHealth, getMeta, getExperiments, runBacktest, generateAlphaIdeas } from "./api";
import { demoExamples, demoAlphas, makeDemoResult } from "./mockData";

const NAV = [
  { id: "workspace", label: "Alpha workspace", icon: LayoutDashboard },
  { id: "create", label: "Create alpha", icon: Plus },
  { id: "saved", label: "Saved alphas", icon: Layers3 },
  { id: "runs", label: "Runs & history", icon: History }
];
const TABS = ["Overview", "Performance", "Risk", "Signal analysis", "Validation", "Yearly", "Universe"];
const fmtPct = (v, digits = 1) => v == null || !Number.isFinite(Number(v)) ? "—" : `${(Number(v) * 100).toFixed(digits)}%`;
const fmtNum = (v, digits = 2) => v == null || !Number.isFinite(Number(v)) ? "—" : Number(v).toFixed(digits);
const chartDate = (s) => s ? s.slice(0, 7) : "";
const safeFile = (s) => (s || "alpha").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

function Status({ status }) {
  const s = String(status || "idle").toLowerCase();
  return <span className={`status status-${s}`}><i />{status || "Idle"}</span>;
}
function Panel({ title, subtitle, action, children, className = "" }) {
  return <section className={`panel ${className}`}><div className="panel-head"><div><h3>{title}</h3>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</section>;
}
function Metric({ label, value, sub, tone, icon: Icon }) {
  return <div className="metric"><div className="metric-label">{label}{Icon && <Icon size={13}/>}</div><div className={`metric-value ${tone || ""}`}>{value}</div>{sub && <div className="metric-sub">{sub}</div>}</div>;
}
function TinySelect({ label, value, onChange, options }) {
  return <label className="field"><span>{label}</span><select value={value} onChange={e => onChange(e.target.value)}>{options.map(o => <option key={o.value || o} value={o.value || o}>{o.label || o}</option>)}</select></label>;
}
function Field({ label, value, onChange, type = "text", options, min, max, step }) {
  return <label className="field"><span>{label}</span>{options
    ? <select value={value} onChange={e => onChange(e.target.value)}>{options.map(o => <option key={o.value || o} value={o.value || o}>{o.label || o}</option>)}</select>
    : <input type={type} value={value} min={min} max={max} step={step} onChange={e => onChange(type === "number" ? e.target.value : e.target.value)} />}</label>;
}
function ChartTip({ active, payload, label, suffix = "%" }) {
  if (!active || !payload?.length) return null;
  return <div className="chart-tip"><strong>{label}</strong>{payload.map(p => <div key={p.dataKey}><i style={{ background: p.color }} />{p.name || p.dataKey}<b>{typeof p.value === "number" ? `${(p.value * (suffix === "%" ? 100 : 1)).toFixed(2)}${suffix}` : p.value}</b></div>)}</div>;
}
function MiniChart({ title, subtitle, data, dataKey, color = "var(--accent)", percent = true, type = "line" }) {
  return <Panel title={title} subtitle={subtitle} className="chart-panel">
    <div className="chart-wrap small-chart"><ResponsiveContainer width="100%" height="100%">
      {type === "bar" ? <BarChart data={data}><CartesianGrid stroke="var(--line)" vertical={false}/><XAxis dataKey="date" tickFormatter={chartDate} tickLine={false} axisLine={false}/><YAxis tickLine={false} axisLine={false} width={43} tickFormatter={v => percent ? `${(v*100).toFixed(0)}%` : v}/><Tooltip content={<ChartTip suffix={percent ? "%" : ""}/>} /><Bar dataKey={dataKey} fill={color} radius={[2,2,0,0]}/></BarChart> :
      <LineChart data={data}><CartesianGrid stroke="var(--line)" vertical={false}/><XAxis dataKey="date" tickFormatter={chartDate} tickLine={false} axisLine={false} minTickGap={28}/><YAxis tickLine={false} axisLine={false} width={43} tickFormatter={v => percent ? `${(v*100).toFixed(0)}%` : v}/><Tooltip content={<ChartTip suffix={percent ? "%" : ""}/>} /><Line type="monotone" dataKey={dataKey} stroke={color} dot={false} strokeWidth={1.8} activeDot={{r:3}}/></LineChart>}
    </ResponsiveContainer></div>
  </Panel>;
}

export default function App() {
  const [page, setPage] = useState("workspace");
  const [mobileNav, setMobileNav] = useState(false);
  const [health, setHealth] = useState("checking");
  const [dataMode, setDataMode] = useState("synthetic");
  const [meta, setMeta] = useState(null);
  const [examples, setExamples] = useState(demoExamples);
  const [alphas, setAlphas] = useState(demoAlphas());
  const [selectedAlpha, setSelectedAlpha] = useState(demoAlphas()[0]);
  const [expression, setExpression] = useState(demoExamples[0].expression);
  const [strategyPrompt, setStrategyPrompt] = useState("");
  const [generatedIdeas, setGeneratedIdeas] = useState([]);
  const [generatingIdeas, setGeneratingIdeas] = useState(false);
  const [generationNote, setGenerationNote] = useState("");
  const [generationOptimization, setGenerationOptimization] = useState(null);
  const [ideaBacktests, setIdeaBacktests] = useState({});
  const [alphaName, setAlphaName] = useState("Momentum z-score");
  const [universe, setUniverse] = useState("NIFTY50");
  const [start, setStart] = useState("2018-01-01");
  const [end, setEnd] = useState("2025-12-31");
  const [portfolio, setPortfolio] = useState("LONG_SHORT");
  const [weighting, setWeighting] = useState("EQUAL_WEIGHT");
  const [holding, setHolding] = useState("1");
  const [executionPrice, setExecutionPrice] = useState("close");
  const [lag, setLag] = useState("1");
  const [cost, setCost] = useState("10");
  const [slippage, setSlippage] = useState("5");
  const [buckets, setBuckets] = useState("10");
  const [k, setK] = useState("10");
  const [longExposure, setLongExposure] = useState("1");
  const [shortExposure, setShortExposure] = useState("1");
  const [positionCap, setPositionCap] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [activeTab, setActiveTab] = useState("Overview");
  const [result, setResult] = useState(() => makeDemoResult());
  const [isDemoResult, setIsDemoResult] = useState(true);
  const [running, setRunning] = useState(false);
  const [toast, setToast] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All statuses");
  const [sortKey, setSortKey] = useState("updated");
  const [showSettings, setShowSettings] = useState(false);
  const [showFieldBrowser, setShowFieldBrowser] = useState(true);
  const [showColumnMenu, setShowColumnMenu] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState(["status","universe","sharpe","ret","turnover","ic","updated"]);
  const [selectedRuns, setSelectedRuns] = useState(["AL-1042","AL-1039"]);
  const [validationOpen, setValidationOpen] = useState({ leakage: true, coverage: true });
  const [history, setHistory] = useState([]);

  const notify = useCallback((msg) => { setToast(msg); window.setTimeout(() => setToast(""), 3000); }, []);
  const refreshHealth = useCallback(async () => {
    setHealth("checking");
    try {
      const h = await getHealth();
      setHealth("connected"); setDataMode(h.data_mode || "unknown");
      const m = await getMeta(); setMeta(m);
      try { const ex = await getExamples(); if (Array.isArray(ex) && ex.length) setExamples(ex); } catch {}
      try { const runs = await getExperiments(); if (Array.isArray(runs)) setHistory(runs); } catch {}
    } catch {
      setHealth("offline"); setMeta(null);
    }
  }, []);
  useEffect(() => { refreshHealth(); }, [refreshHealth]);

  const series = useMemo(() => (result?.series?.dates || []).map((date, i) => ({
    date, gross: result.series.cum_gross?.[i], cumNet: result.series.cum_net?.[i],
    drawdown: result.series.drawdown?.[i], sharpe: result.series.rolling_sharpe?.[i],
    turnover: result.series.turnover?.[i], long: result.series.long?.[i],
    short: result.series.short?.[i], netExposure: result.series.net?.[i],
    ic: result.ic?.values?.[i], rollingIC: result.ic?.rolling?.[i]
  })), [result]);
  const filteredAlphas = useMemo(() => alphas.filter(a => {
    const matches = `${a.name} ${a.expression} ${a.id} ${(a.tags || []).join(" ")}`.toLowerCase().includes(search.toLowerCase());
    return matches && (statusFilter === "All statuses" || a.status === statusFilter);
  }).sort((a,b) => sortKey === "sharpe" ? (b.sharpe || -Infinity) - (a.sharpe || -Infinity) : String(b[sortKey] || "").localeCompare(String(a[sortKey] || ""))), [alphas, search, statusFilter, sortKey]);

  const applyAlpha = (alpha) => {
    setSelectedAlpha(alpha); setExpression(alpha.expression); setAlphaName(alpha.name); setUniverse(alpha.universe || "NIFTY50");
    setPage("create"); setMobileNav(false);
  };
  const useExample = (ex) => { setExpression(ex.expression); setAlphaName(ex.name); setPage("create"); notify(`Loaded template: ${ex.name}`); };
  const saveAlpha = () => {
    const id = selectedAlpha?.id || `AL-${Math.floor(1000 + Math.random()*8999)}`;
    const item = { ...(selectedAlpha || {}), id, name: alphaName || "Untitled alpha", expression, status: "Draft", universe, updated: "Just now", tags: selectedAlpha?.tags || [] };
    setAlphas(old => [item, ...old.filter(a => a.id !== id)]);
    setSelectedAlpha(item); notify("Alpha draft saved in this browser.");
  };
  const buildPayload = () => ({
    expression, universe, start, end, holding_period: Number(holding), portfolio, weighting,
    transaction_cost_bps: Number(cost), slippage_bps: Number(slippage),
    execution_lag_bars: Number(lag), execution_price: executionPrice,
    n_buckets: Number(buckets), k: Number(k),
    long_exposure: Number(longExposure), short_exposure: Number(shortExposure),
    ...(positionCap !== "" ? { max_position_weight: Number(positionCap) } : {})
  });
  const simulate = async () => {
    if (!expression.trim()) { notify("Enter an alpha expression before running."); return; }
    if (start > end) { notify("Start date must be before the end date."); return; }
    setRunning(true);
    try {
      const live = await runBacktest(buildPayload());
      setResult(live); setIsDemoResult(false); setHealth("connected");
      notify(`Backtest completed in ${live.elapsed_s ?? "—"}s.`);
    } catch (err) {
      const demo = makeDemoResult(expression, { universe, start, end, holding_period: holding, portfolio, weighting });
      setResult(demo); setIsDemoResult(true);
      notify(`API unavailable — showing illustrative demo results. ${err.message}`);
    } finally {
      setRunning(false); setPage("results"); setActiveTab("Overview");
      setHistory(old => [{ experiment_id: result?.experiment_id || `demo-${Date.now()}`, status: "success", expression, created_at: new Date().toISOString() }, ...old].slice(0, 30));
    }
  };
  const generateIdeas = async () => {
    if (strategyPrompt.trim().length < 20) { notify("Describe your strategy in a little more detail (at least 20 characters)."); return; }
    setGeneratingIdeas(true); setGeneratedIdeas([]); setGenerationNote(""); setGenerationOptimization(null); setIdeaBacktests({});
    try {
      const response = await generateAlphaIdeas({ idea: strategyPrompt, universe, start, end });
      setGeneratedIdeas(response.ideas || []); setGenerationNote(response.note || "Review each hypothesis and its limitations before running it."); setGenerationOptimization(response.optimization || null);
      notify(`Gemini generated ${(response.ideas || []).length} validated candidate ideas.`);
    } catch (err) { setGenerationNote(err.message); notify(`Idea generation failed: ${err.message}`); }
    finally { setGeneratingIdeas(false); }
  };
  const selectGeneratedIdea = (idea) => {
    setExpression(idea.expression); setAlphaName(idea.name || "Gemini-generated alpha"); setSelectedAlpha(null);
    setPage("create"); notify("Expression loaded. Review it and the backtest settings before running.");
  };
  const backtestGeneratedIdea = async (idea) => {
    setIdeaBacktests(old => ({ ...old, [idea.id]: { status: "running" } }));
    try {
      const out = await runBacktest({ ...buildPayload(), expression: idea.expression });
      setIdeaBacktests(old => ({ ...old, [idea.id]: { status: "success", result: out } }));
      setHistory(old => [{ experiment_id: out.experiment_id, status: "success", expression: idea.expression, created_at: new Date().toISOString() }, ...old].slice(0, 30));
    } catch (err) { setIdeaBacktests(old => ({ ...old, [idea.id]: { status: "error", error: err.message } })); }
  };
  const exportJSON = () => {
    const blob = new Blob([JSON.stringify({ result, demo: isDemoResult }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob); const a = document.createElement("a");
    a.href = url; a.download = `${safeFile(alphaName)}-result.json`; a.click(); URL.revokeObjectURL(url);
  };
  const exportCSV = () => {
    const rows = [["date","gross_return","net_return","drawdown","rolling_sharpe","turnover","ic"], ...series.map(s => [s.date,s.gross,s.net,s.drawdown,s.sharpe,s.turnover,s.ic])];
    const blob = new Blob([rows.map(r => r.join(",")).join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob); const a = document.createElement("a");
    a.href = url; a.download = `${safeFile(alphaName)}-series.csv`; a.click(); URL.revokeObjectURL(url);
  };
  const copyCurl = async () => {
    const text = `curl -X POST http://localhost:3000/api/backtest -H 'Content-Type: application/json' -d '${JSON.stringify(buildPayload())}'`;
    try { await navigator.clipboard.writeText(text); notify("cURL copied to clipboard."); } catch { notify(text); }
  };
  const toggleRun = (id) => setSelectedRuns(old => old.includes(id) ? old.filter(x => x !== id) : [...old, id]);
  const insertField = (field) => { setExpression(v => `${v}${v.trim() ? " " : ""}${field}`); setPage("create"); };
  const nav = (id) => { setPage(id); setMobileNav(false); };
  const demo = isDemoResult || result?.data_mode === "synthetic";
  const s = result?.summary || {};
  const chartTabs = ["Overview","Performance","Risk","Signal analysis","Validation","Yearly","Universe"];

  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
      <div className="brand"><div className="brand-mark"><Activity size={19}/></div><div><strong>Unified<span>Backtester</span></strong><small>QUANT RESEARCH</small></div><button className="icon-btn sidebar-close" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X size={17}/></button></div>
      <div className="nav-label">WORKSPACE</div>
      <nav className="nav-list">{NAV.map(({id,label,icon:Icon}) => <button key={id} className={`nav-item ${page === id || (id === "create" && page === "results") ? "active" : ""}`} onClick={() => nav(id)}><Icon size={16}/><span>{label}</span>{id === "runs" && <em>{history.length || 4}</em>}</button>)}</nav>
      <div className="nav-label section-label">APPLICATIONS</div>
      <button className="nav-item" onClick={() => notify("Screener integration is available after the existing app/API audit.")}><ListFilter size={16}/><span>Screeners</span><span className="external-dot"/></button>
      <button className="nav-item disabled" onClick={() => notify("Investment tools are planned for a later release.")}><BarChart3 size={16}/><span>Investment</span><small>Later</small></button>
      <div className="sidebar-divider"/>
      <div className="nav-label">QUICK TEMPLATES</div>
      <div className="template-list">{examples.slice(0,4).map(ex => <button key={ex.name} className="template-item" onClick={() => useExample(ex)}><span className="template-dot"/><span>{ex.name}</span></button>)}</div>
      <div className="sidebar-spacer"/>
      <div className="sidebar-status"><span className={`connection-dot ${health}`}/><div><strong>{health === "connected" ? "Engine connected" : health === "checking" ? "Checking engine…" : "Demo mode"}</strong><small>{health === "connected" ? `API online · ${dataMode}` : "Local preview available"}</small></div><button className="icon-btn" title="Retry connection" onClick={refreshHealth}><RefreshCw size={14}/></button></div>
    </aside>
    {mobileNav && <button className="mobile-scrim" onClick={() => setMobileNav(false)} aria-label="Close navigation overlay"/>}
    <main className="main-area">
      <header className="topbar">
        <div className="topbar-left"><button className="icon-btn menu-btn" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={18}/></button><div className="breadcrumbs"><span>Research</span><ChevronRight size={13}/><strong>{page === "workspace" ? "Alpha workspace" : page === "create" ? "Create alpha" : page === "results" ? "Run results" : page === "saved" ? "Saved alphas" : page === "runs" ? "Runs & history" : page}</strong></div></div>
        <div className="topbar-actions"><div className={`api-pill ${health}`}><span className="connection-dot"/>{health === "connected" ? "API connected" : health === "checking" ? "Connecting" : "API offline"}</div><button className="icon-btn" title="Notifications" onClick={() => notify("You're all caught up.")}><Bell size={16}/></button></div>
      </header>

      {page === "workspace" && <section className="page-content">
        <div className="page-title-row"><div><div className="eyebrow"><span className="eyebrow-line"/> ALPHA RESEARCH</div><h1>Alpha workspace</h1><p className="page-subtitle">Build signals, run experiments, inspect evidence.</p></div><div className="title-actions"><button className="btn btn-secondary" onClick={() => nav("runs")}><History size={15}/> Run history</button><button className="btn btn-primary" onClick={() => {setAlphaName("Untitled alpha");setExpression("");setSelectedAlpha(null);nav("create");}}><Plus size={16}/> Create alpha</button></div></div>
        <div className="stat-strip">
          <Metric label="Saved alphas" value={String(alphas.length).padStart(2,"0")} sub="Across this workspace" icon={Layers3}/>
          <Metric label="Completed runs" value="24" sub="Last 30 days" icon={CheckCircle2}/>
          <Metric label="Avg. net Sharpe" value="1.18" sub={<span className="positive-text"><ArrowUpRight size={12}/> +0.12 vs prior period</span>} icon={Gauge}/>
          <Metric label="Runs in queue" value="01" sub="1 running · 0 queued" icon={Clock3}/>
        </div>
        <Panel title="Your alphas" subtitle="Saved expressions and their latest completed run." action={<div className="panel-actions"><button className="btn btn-quiet" onClick={() => setShowColumnMenu(!showColumnMenu)}><SlidersHorizontal size={14}/> Columns</button><button className="btn btn-quiet" onClick={() => nav("saved")}>View all <ChevronRight size={14}/></button>{showColumnMenu && <div className="column-menu">{["status","universe","sharpe","ret","turnover","ic","updated"].map(c => <label key={c}><input type="checkbox" checked={visibleColumns.includes(c)} onChange={() => setVisibleColumns(old => old.includes(c) ? old.filter(x=>x!==c) : [...old,c])}/>{({status:"Status",universe:"Universe",sharpe:"Sharpe",ret:"Net return",turnover:"Turnover",ic:"IC mean",updated:"Updated"})[c]}</label>)}</div>}</div>}>
          <div className="table-toolbar"><div className="search-box"><Search size={15}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search alphas, expressions, tags…"/></div><select className="toolbar-select" value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}><option>All statuses</option><option>Ready</option><option>Warning</option><option>Running</option><option>Failed</option><option>Draft</option></select><button className="icon-btn bordered" title="Filter"><Filter size={15}/></button></div>
          <div className="table-scroll"><table className="data-table"><thead><tr><th>Alpha name</th>{visibleColumns.includes("status")&&<th>Status</th>}{visibleColumns.includes("universe")&&<th>Universe</th>}{visibleColumns.includes("sharpe")&&<th onClick={()=>setSortKey("sharpe")} className="sortable">Net Sharpe ↕</th>}{visibleColumns.includes("ret")&&<th onClick={()=>setSortKey("ret")} className="sortable">Net return ↕</th>}{visibleColumns.includes("turnover")&&<th>Turnover</th>}{visibleColumns.includes("ic")&&<th>IC mean</th>}{visibleColumns.includes("updated")&&<th>Updated</th>}<th/></tr></thead><tbody>{filteredAlphas.slice(0,8).map(a=><tr key={a.id} onClick={()=>applyAlpha(a)} className="clickable-row"><td><div className="alpha-cell"><div className="alpha-icon"><Code2 size={15}/></div><div><strong>{a.name}</strong><small className="mono">{a.id} · {a.expression}</small><div className="tag-row">{(a.tags||[]).slice(0,2).map(t=><span className="tag" key={t}>{t}</span>)}</div></div></div></td>{visibleColumns.includes("status")&&<td><Status status={a.status}/></td>}{visibleColumns.includes("universe")&&<td><span className="universe-chip">{a.universe}</span></td>}{visibleColumns.includes("sharpe")&&<td className="mono number">{fmtNum(a.sharpe)}</td>}{visibleColumns.includes("ret")&&<td className={`mono number ${a.ret > 0 ? "positive-text" : ""}`}>{a.ret == null ? "—" : `${a.ret.toFixed(1)}%`}</td>}{visibleColumns.includes("turnover")&&<td className="mono number">{a.turnover ?? "—"}</td>}{visibleColumns.includes("ic")&&<td className="mono number">{fmtNum(a.ic,3)}</td>}{visibleColumns.includes("updated")&&<td className="muted">{a.updated}</td>}<td><button className="icon-btn row-menu" title="Open alpha" onClick={e=>{e.stopPropagation();applyAlpha(a);}}><ChevronRight size={15}/></button></td></tr>)}</tbody></table></div>
          <div className="table-foot"><span>Showing {Math.min(filteredAlphas.length,8)} of {filteredAlphas.length} alphas <span className="demo-inline">· Preview dataset</span></span><div><button className="icon-btn" disabled><ChevronLeft size={15}/></button><button className="page-num">1</button><button className="icon-btn" disabled><ChevronRight size={15}/></button></div></div>
        </Panel>
        <div className="two-col lower-panels">
          <Panel title="Recent runs" subtitle="Latest experiment activity" action={<button className="btn btn-quiet" onClick={()=>nav("runs")}>View history <ChevronRight size={14}/></button>}>
            <div className="run-list">{[
              {name:"Momentum z-score",id:"run_8fa2c1",status:"Succeeded",time:"Today, 09:42",tone:"green"},
              {name:"Sector-neutral momentum",id:"run_7c20e4",status:"Succeeded",time:"Yesterday, 18:16",tone:"green"},
              {name:"Short-term reversal",id:"run_6ab91d",status:"Warning",time:"Oct 15, 14:08",tone:"amber"}
            ].map(r=><div className="run-row" key={r.id}><div className={`run-symbol ${r.tone}`}><Activity size={15}/></div><div className="run-info"><strong>{r.name}</strong><small className="mono">{r.id} · {r.time}</small></div><Status status={r.status}/><button className="icon-btn" onClick={()=>nav("results")}><ChevronRight size={14}/></button></div>)}</div>
          </Panel>
          <Panel title="Starter templates" subtitle="Begin with a known expression">
            <div className="starter-grid">{examples.slice(0,4).map(ex=><button key={ex.name} className="starter-card" onClick={()=>useExample(ex)}><div><Sparkles size={15}/><span>{ex.category || "Template"}</span></div><strong>{ex.name}</strong><code>{ex.expression}</code><span className="starter-open">Use template <ArrowUpRight size={13}/></span></button>)}</div>
          </Panel>
        </div>
      </section>}

      {page === "create" && <section className="page-content">
        <div className="page-title-row compact-title"><div><div className="eyebrow"><span className="eyebrow-line"/> RESEARCH EDITOR</div><h1>{alphaName || "Untitled alpha"}</h1><p className="page-subtitle">Edit your signal and configure an immutable experiment snapshot.</p></div><div className="title-actions"><span className="autosave"><span/> Draft changes</span><button className="btn btn-secondary" onClick={saveAlpha}><Check size={15}/> Save alpha</button><button className="btn btn-primary" onClick={simulate} disabled={running}>{running?<RefreshCw className="spin" size={15}/>:<Play size={15} fill="currentColor"/>}{running?"Running…":"Run backtest"}</button></div></div>
        <Panel title="Describe your strategy — Gemini Alpha Assistant" subtitle="No expression-writing skills required. Explain the market behavior you want to capture; Gemini proposes candidates using only the engine's registered fields and operators." className="idea-assistant-panel">
          <div className="idea-prompt-row">
            <div className="idea-prompt-input"><label htmlFor="strategy-prompt">Your strategy in plain English</label><textarea id="strategy-prompt" value={strategyPrompt} onChange={e=>setStrategyPrompt(e.target.value)} placeholder="Example: Find liquid stocks where medium-term momentum is strong but recent volatility is falling. I want a daily long/short signal, avoid chasing sudden spikes, and prefer signals that are stable over several weeks." rows={4}/><div className="prompt-helper"><Sparkles size={13}/> Be specific about the market behavior, holding horizon, and what you want to avoid. Daily OHLCV data only unless the engine supports more.</div></div>
            <div className="idea-prompt-actions"><button className="btn btn-primary" onClick={generateIdeas} disabled={generatingIdeas}>{generatingIdeas?<RefreshCw className="spin" size={15}/>:<Sparkles size={15}/>}{generatingIdeas?"Generating ideas…":"Generate alpha ideas"}</button><small>Powered by Gemini · API key stays on the backend</small><button className="btn btn-quiet" onClick={()=>setStrategyPrompt("Find stocks with persistent 20-day momentum, but reduce the score when recent volatility is unusually high. I want a daily cross-sectional long/short strategy using only price and volume data.")}>Use example prompt</button></div>
          </div>
          {generationNote && <div className={`generation-note ${generatedIdeas.length ? "success-note" : "error-note"}`}>{generationNote}</div>}
          {generationOptimization && <div className="generation-note success-note"><strong>Prompt optimization:</strong> {generationOptimization.compression_used ? "Long prompt compressed" : "Compression skipped"} · ~{generationOptimization.original_input_tokens_est} original input tokens · ~{generationOptimization.final_prompt_tokens_est} final prompt tokens · {generationOptimization.context_fields_count}/{generationOptimization.context_fields_available} fields included{generationOptimization.compression_elapsed_s ? ` · compression ${generationOptimization.compression_elapsed_s}s` : ""}. Estimates only; check provider usage for exact billing.</div>}
          {generatedIdeas.length > 0 && <div className="generated-ideas"><div className="generated-ideas-head"><div><strong>Candidate alpha ideas</strong><span>{generatedIdeas.length} candidates · syntax/registry checked, not yet proven profitable</span></div><span className="validation-chip"><ShieldCheck size={13}/> Engine fields checked</span></div>
            {generatedIdeas.map((idea, idx) => { const bt=ideaBacktests[idea.id]; return <article className="generated-idea-card" key={idea.id || idx}><div className="generated-idea-top"><span className="idea-index">0{idx+1}</span><div className="generated-idea-copy"><h4>{idea.name}</h4><p>{idea.hypothesis}</p></div><Status status={bt?.status === "success" ? "Backtested" : bt?.status === "running" ? "Running" : bt?.status === "error" ? "Failed" : "Candidate"}/></div><code className="generated-expression">{idea.expression}</code><div className="generated-idea-details"><div><strong>Why it might work</strong><p>{idea.rationale}</p></div><div><strong>Expected behavior</strong><p>{idea.expected_behavior}</p></div><div><strong>Risks & caveats</strong><p>{Array.isArray(idea.risks) ? idea.risks.join(" ") : idea.risks}</p></div></div>{bt?.status === "success" && <div className="candidate-result-strip"><span>Net Sharpe <b>{fmtNum(bt.result?.summary?.sharpe_net)}</b></span><span>Annual net return <b>{fmtPct(bt.result?.summary?.annual_return_net)}</b></span><span>Max drawdown <b>{fmtPct(bt.result?.summary?.max_drawdown)}</b></span></div>}{bt?.status === "error" && <p className="candidate-error">Backtest failed: {bt.error}</p>}<div className="generated-idea-actions"><button className="btn btn-secondary" onClick={()=>selectGeneratedIdea(idea)}>Open in expression editor</button><button className="btn btn-primary" disabled={bt?.status === "running"} onClick={()=>backtestGeneratedIdea(idea)}>{bt?.status === "running"?<RefreshCw className="spin" size={14}/>:<Play size={14}/>}{bt?.status === "running"?"Backtesting…":bt?.status === "success"?"Run again":"Backtest this idea"}</button></div></article>})}
          </div>}
        </Panel>
        <div className="editor-layout">
          <div className="editor-main">
            <Panel title="Expression editor" subtitle="The expression is the source of truth. Use engine fields and operators." action={<div className="panel-actions"><button className="btn btn-quiet" onClick={()=>setExpression(v=>v.trim())}>Format</button><button className="btn btn-quiet" onClick={()=>notify(expression.trim() ? "Basic preflight passed. Server validation runs on submission." : "Expression cannot be empty.")}><ShieldCheck size={14}/> Validate</button></div>}>
              <div className="alpha-name-field"><label>Alpha name</label><input value={alphaName} onChange={e=>setAlphaName(e.target.value)} placeholder="Give this alpha a name"/></div>
              <div className="code-editor"><div className="line-numbers">{expression.split("\n").map((_,i)=><span key={i}>{String(i+1).padStart(2,"0")}</span>)}</div><textarea spellCheck="false" value={expression} onChange={e=>setExpression(e.target.value)} aria-label="Alpha expression editor" placeholder="rank(ts_zscore(momentum_20, 20))"/><div className="editor-watermark"><Command size={12}/> Enter expression · ⌘ + Enter to run</div></div>
              <div className="editor-foot"><span><span className="syntax-dot"/> Expression text</span><span>{expression.length} chars</span><span>{expression.trim() ? "Draft ready" : "Expression required"}</span></div>
            </Panel>
            <Panel title="Run preflight" subtitle="Checks before submitting an experiment">
              <div className="preflight-grid"><div className="preflight-item"><CheckCircle2 size={16} className="green"/><div><strong>Configuration shape</strong><small>Required settings present</small></div><Status status="Passed"/></div><div className="preflight-item"><CircleHelp size={16} className={expression.trim()?"blue":"amber"}/><div><strong>Expression validation</strong><small>{health==="connected"?"Validated by the engine on run":"Server validation unavailable in preview"}</small></div><Status status={health==="connected"?"Ready":"Pending"}/></div><div className="preflight-item"><AlertTriangle size={16} className="amber"/><div><strong>Data limitations</strong><small>Point-in-time and survivorship metadata will be attached to results</small></div><Status status="Review"/></div></div>
            </Panel>
          </div>
          <aside className="settings-column">
            <Panel title="Backtest settings" subtitle="Frozen into each submitted run" action={<button className="icon-btn" title="Reset settings" onClick={()=>{setUniverse("NIFTY50");setStart("2018-01-01");setEnd("2025-12-31");setHolding("1");setCost("10");setSlippage("5");setLag("1");notify("Settings reset.");}}><RefreshCw size={14}/></button>}>
              <div className="settings-body">
                <div className="setting-section"><div className="setting-heading"><span>01</span><strong>Universe & period</strong></div><div className="field"><span>Universe</span><div className="fixed-universe">NIFTY50 <small>Only enabled universe</small></div></div><div className="field-grid"><Field label="Start date" type="date" value={start} onChange={setStart}/><Field label="End date" type="date" value={end} onChange={setEnd}/></div>{meta?.data_range?.min && <small className="field-hint">Available: {meta.data_range.min} — {meta.data_range.max}</small>}</div>
                <div className="setting-section"><div className="setting-heading"><span>02</span><strong>Portfolio construction</strong></div><Field label="Portfolio type" value={portfolio} onChange={setPortfolio} options={(meta?.portfolio_types || ["LONG_SHORT","LONG_ONLY","TOP_K","BOTTOM_K","TOP_BOTTOM","QUANTILE"]).map(v=>({value:v,label:v.replaceAll("_"," ")}))}/><Field label="Weighting scheme" value={weighting} onChange={setWeighting} options={(meta?.weighting_schemes || ["EQUAL_WEIGHT","SIGNAL_WEIGHTED","RANK_WEIGHTED","NORMALIZED_SIGNAL"]).map(v=>({value:v,label:v.replaceAll("_"," ")}))}/><div className="field-grid"><Field label="Long exposure" type="number" min="0" step=".1" value={longExposure} onChange={setLongExposure}/><Field label="Short exposure" type="number" min="0" step=".1" value={shortExposure} onChange={setShortExposure}/></div></div>
                <div className="setting-section"><div className="setting-heading"><span>03</span><strong>Execution & costs</strong></div><div className="field-grid"><Field label="Holding period" type="number" min="1" value={holding} onChange={setHolding}/><Field label="Execution lag" type="number" min="0" value={lag} onChange={setLag}/></div><Field label="Execution price" value={executionPrice} onChange={setExecutionPrice} options={[{value:"close",label:"Close"},{value:"open",label:"Open"}]}/><div className="field-grid"><Field label="Transaction cost (bps)" type="number" min="0" value={cost} onChange={setCost}/><Field label="Slippage (bps)" type="number" min="0" value={slippage} onChange={setSlippage}/></div></div>
                <button className="advanced-toggle" onClick={()=>setShowAdvanced(!showAdvanced)}><SlidersHorizontal size={14}/><span>Advanced settings</span>{showAdvanced?<ChevronDown size={15}/>:<ChevronRight size={15}/>}</button>
                {showAdvanced && <div className="setting-section advanced-fields"><div className="field-grid"><Field label="Quantile buckets" type="number" min="2" value={buckets} onChange={setBuckets}/><Field label="K (top/bottom)" type="number" min="1" value={k} onChange={setK}/></div><Field label="Max position weight (optional)" type="number" min=".01" max="1" step=".01" value={positionCap} onChange={setPositionCap}/><small className="field-hint">Leave blank to use the engine default.</small></div>}
                <div className="run-cta"><button className="btn btn-primary full-width" onClick={simulate} disabled={running}>{running?<RefreshCw className="spin" size={15}/>:<Play size={15} fill="currentColor"/>}{running?"Submitting run…":"Run backtest"}<span>⌘ ↵</span></button><small><ShieldCheck size={12}/> Each run stores a separate configuration snapshot.</small></div>
              </div>
            </Panel>
            <Panel title="Field & operator browser" subtitle="Click to insert into the editor" action={<button className="icon-btn" onClick={()=>setShowFieldBrowser(!showFieldBrowser)}>{showFieldBrowser?<ChevronDown size={14}/>:<ChevronRight size={14}/>}</button>}>
              {showFieldBrowser && <FieldBrowser meta={meta} insertField={insertField}/>}
            </Panel>
          </aside>
        </div>
      </section>}

      {page === "results" && <section className="page-content">
        <div className="page-title-row compact-title"><div><div className="eyebrow"><span className="eyebrow-line"/> EXPERIMENT RESULT</div><div className="result-title"><h1>{alphaName}</h1><Status status="Succeeded"/></div><p className="page-subtitle"><span className="mono">{result?.experiment_id || "run-preview"}</span> · {result?.config?.universe || universe} · {result?.config?.start || start} — {result?.config?.end || end}</p></div><div className="title-actions"><button className="btn btn-secondary" onClick={exportJSON}><FileJson size={15}/> Export JSON</button><button className="btn btn-secondary" onClick={exportCSV}><Download size={15}/> CSV</button><button className="btn btn-primary" onClick={()=>{setPage("create");}}><Play size={14}/> Rerun</button></div></div>
        {demo && <div className="notice warning-notice"><AlertTriangle size={16}/><div><strong>Illustrative preview data</strong><p>This chart set is dummy/synthetic data, not evidence about real market performance. Connect the API and run the expression to view engine output.</p></div><button className="btn btn-quiet" onClick={refreshHealth}>Retry API <RefreshCw size={13}/></button></div>}
        <div className="expression-snapshot"><div><span>EXPRESSION SNAPSHOT</span><code>{result?.config?.expression || expression}</code></div><button className="btn btn-quiet" onClick={copyCurl}><Copy size={14}/> Copy cURL</button></div>
        <div className="result-tabs">{chartTabs.map(t=><button key={t} className={activeTab===t?"selected":""} onClick={()=>setActiveTab(t)}>{t}</button>)}</div>
        <div className="metric-grid result-metrics">
          <Metric label="Net annual return" value={fmtPct(s.annual_return_net)} sub={`Gross ${fmtPct(s.annual_return_gross)}`} tone={s.annual_return_net >= 0 ? "positive-text" : "negative-text"}/>
          <Metric label="Net Sharpe" value={fmtNum(s.sharpe_net)} sub={`Gross ${fmtNum(s.sharpe_gross)}`} tone={s.sharpe_net>=1?"positive-text":""}/>
          <Metric label="Sortino ratio" value={fmtNum(s.sortino)} sub="Downside-adjusted"/>
          <Metric label="Max drawdown" value={fmtPct(s.max_drawdown)} sub="Peak-to-trough" tone="negative-text"/>
          <Metric label="Annual turnover" value={fmtNum(s.turnover_annual)} sub="One-way · annualized"/>
          <Metric label="IC mean" value={fmtNum(s.ic_mean,3)} sub={`IC IR ${fmtNum(s.ic_ir)}`}/>
          <Metric label="Fitness" value={fmtNum(s.fitness)} sub="Derived engine metric"/>
        </div>
        {(activeTab==="Overview" || activeTab==="Performance") && <Panel title="Cumulative returns" subtitle={`Net and gross portfolio return · ${result?.series?.dates?.[0] || start} to ${result?.series?.dates?.at(-1) || end}`} action={<span className="chart-legend"><i className="legend-cyan"/> Net return <i className="legend-violet"/> Gross return</span>}>
          <div className="chart-wrap main-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={series}><defs><linearGradient id="netFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--accent)" stopOpacity={.2}/><stop offset="100%" stopColor="var(--accent)" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="var(--line)" vertical={false}/><XAxis dataKey="date" tickFormatter={chartDate} tickLine={false} axisLine={false} minTickGap={40}/><YAxis tickFormatter={v=>`${(v*100).toFixed(0)}%`} tickLine={false} axisLine={false} width={52}/><Tooltip content={<ChartTip/>}/><ReferenceLine y={0} stroke="var(--line-strong)"/><Area type="monotone" dataKey="cumNet" name="Net return" stroke="var(--accent)" fill="url(#netFill)" strokeWidth={2} dot={false}/><Line type="monotone" dataKey="gross" name="Gross return" stroke="var(--violet)" strokeWidth={1.7} dot={false}/></AreaChart></ResponsiveContainer></div>
        </Panel>}
        <div className="chart-grid">
          {(activeTab==="Overview" || activeTab==="Risk") && <MiniChart title="Drawdown" subtitle="Peak-to-trough decline" data={series} dataKey="drawdown" color="var(--red)"/>}
          {(activeTab==="Overview" || activeTab==="Risk") && <MiniChart title="Rolling Sharpe" subtitle="60-day rolling window" data={series} dataKey="sharpe" color="var(--accent)" percent={false}/>}
          {(activeTab==="Overview" || activeTab==="Signal analysis") && <MiniChart title="Information coefficient" subtitle="Daily rank correlation" data={series} dataKey="ic" color="var(--green)" percent={false} type="bar"/>}
          {(activeTab==="Overview" || activeTab==="Signal analysis") && <MiniChart title="Turnover" subtitle="Daily one-way turnover" data={series} dataKey="turnover" color="var(--violet)" percent={false}/>}
          {(activeTab==="Overview" || activeTab==="Risk") && <Panel title="Exposure over time" subtitle="Long, short and net exposure"><div className="chart-wrap small-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={series}><CartesianGrid stroke="var(--line)" vertical={false}/><XAxis dataKey="date" tickFormatter={chartDate} tickLine={false} axisLine={false}/><YAxis tickLine={false} axisLine={false} width={42}/><Tooltip content={<ChartTip suffix=""/>}/><Legend/><Line dataKey="long" name="Long" stroke="var(--green)" dot={false}/><Line dataKey="short" name="Short" stroke="var(--red)" dot={false}/><Line dataKey="netExposure" name="Net" stroke="var(--accent)" dot={false}/></LineChart></ResponsiveContainer></div></Panel>}
        </div>
        {(activeTab==="Overview" || activeTab==="Signal analysis") && <div className="two-col">
          <Panel title="Quantile analysis" subtitle="Average forward return by signal bucket"><div className="chart-wrap quantile-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={result?.quantiles || []}><CartesianGrid stroke="var(--line)" vertical={false}/><XAxis dataKey="bucket" tickLine={false} axisLine={false}/><YAxis tickFormatter={v=>`${v.toFixed(1)}%`} tickLine={false} axisLine={false} width={48}/><Tooltip content={<ChartTip suffix="%"/>}/><ReferenceLine y={0} stroke="var(--line-strong)"/><Bar dataKey="avg_return" name="Avg. return" fill="var(--accent)" radius={[2,2,0,0]}/></BarChart></ResponsiveContainer></div></Panel>
          <Panel title="Year-by-year performance" subtitle="Annualized summary by calendar year"><div className="table-scroll"><table className="data-table compact-table"><thead><tr><th>Year</th><th>Return</th><th>Sharpe</th><th>Volatility</th><th>Max DD</th><th>IC</th></tr></thead><tbody>{(result?.yearly || []).map(y=><tr key={y.year}><td className="mono">{y.year}</td><td className={y.return>=0?"positive-text":"negative-text"}>{y.return}%</td><td className="mono">{y.sharpe}</td><td>{y.volatility ?? y.vol}%</td><td className="negative-text">{y.maxDD ?? y.max_drawdown}%</td><td className="mono">{y.ic}</td></tr>)}</tbody></table></div></Panel>
        </div>}
        {(activeTab==="Validation" || activeTab==="Overview") && <Panel title="Validation & research checks" subtitle="Evidence and limitations associated with this result" action={<div className="validation-counts"><span className="count pass">4 passed</span><span className="count warn">2 warnings</span><span className="count pending">1 pending</span></div>}>
          <div className="validation-list">
            {[{id:"leakage",name:"Look-ahead / leakage diagnostics",status:"Warning",desc:"Review signal alignment and availability timestamps. A passing syntax check does not prove absence of leakage.",evidence:"Signal shifted by configured execution lag; alternative data timestamp audit must be verified."},{id:"coverage",name:"Universe coverage & data quality",status:"Passed",desc:"Coverage is checked across the requested universe and date window.",evidence:`Average coverage: ${fmtPct(s.coverage_avg)}. Synthetic preview values are illustrative.`},{id:"walk",name:"Walk-forward validation",status:"Pending",desc:"Rolling train and test windows evaluate stability across time.",evidence:"This preview does not execute the engine validation child task."},{id:"survivorship",name:"Survivorship / point-in-time risk",status:"Warning",desc:"Current universe constituents may not represent historical membership.",evidence:"Do not interpret synthetic or current-constituent backtests as survivorship-safe."}].map(v=><div className="validation-item" key={v.id}><button className="validation-head" onClick={()=>setValidationOpen(o=>({...o,[v.id]:!o[v.id]}))}><span className={`validation-icon ${v.status.toLowerCase()}`}>{v.status==="Passed"?<Check size={14}/>:v.status==="Warning"?<AlertTriangle size={14}/>:<Clock3 size={14}/>}</span><span className="validation-name"><strong>{v.name}</strong><small>{v.desc}</small></span><Status status={v.status}/>{validationOpen[v.id]?<ChevronDown size={15}/>:<ChevronRight size={15}/>}</button>{validationOpen[v.id]&&<div className="validation-evidence"><strong>Evidence / notes</strong><p>{v.evidence}</p></div>}</div>)}
          </div>
        </Panel>}
        {(activeTab==="Yearly") && <Panel title="Year-by-year performance" subtitle="Annual performance breakdown"><div className="table-scroll"><table className="data-table"><thead><tr><th>Year</th><th>Return</th><th>Sharpe</th><th>Volatility</th><th>Max drawdown</th><th>Turnover</th><th>IC</th><th>Days</th></tr></thead><tbody>{(result?.yearly||[]).map(y=><tr key={y.year}><td>{y.year}</td><td>{y.return}%</td><td>{y.sharpe}</td><td>{y.volatility ?? y.vol}%</td><td>{y.maxDD ?? y.max_drawdown}%</td><td>{y.turnover}</td><td>{y.ic}</td><td>{y.days}</td></tr>)}</tbody></table></div></Panel>}
        {activeTab==="Universe" && <Panel title="Universe & data audit" subtitle="Metadata available from the selected provider"><div className="audit-grid"><div><small>Universe</small><strong>{result?.universe?.name || universe}</strong></div><div><small>Construction</small><strong>{result?.universe?.construction || "Preset"}</strong></div><div><small>Asset count</small><strong>{result?.universe?.n_assets || "—"}</strong></div><div><small>Point-in-time</small><strong className="amber-text">{String(result?.universe?.point_in_time ?? "Unknown")}</strong></div></div>{(result?.warnings||[]).map(w=><div className="notice warning-notice slim" key={w}><AlertTriangle size={15}/><span>{w}</span></div>)}</Panel>}
        <footer className="result-footer"><span><Database size={13}/> Data mode: {result?.data_mode || "unknown"}</span><span><Clock3 size={13}/> Runtime: {result?.elapsed_s ?? "—"}s</span><span><ShieldCheck size={13}/> Run snapshot: immutable</span></footer>
      </section>}

      {(page === "saved" || page === "runs") && <section className="page-content">
        <div className="page-title-row"><div><div className="eyebrow"><span className="eyebrow-line"/> RESEARCH LIBRARY</div><h1>{page==="saved"?"Saved alphas":"Runs & history"}</h1><p className="page-subtitle">{page==="saved"?"Manage reusable expressions and draft versions.":"Inspect run status, immutable snapshots and experiment outputs."}</p></div><div className="title-actions"><button className="btn btn-primary" onClick={()=>{setAlphaName("Untitled alpha");setExpression("");setSelectedAlpha(null);nav("create");}}><Plus size={15}/> New alpha</button></div></div>
        <Panel title={page==="saved"?"Alpha library":"Experiment history"} subtitle={page==="saved"?"Saved expressions in this workspace":"Recent runs in this browser preview"} action={<button className="btn btn-secondary" onClick={()=>page==="saved"?saveAlpha():refreshHealth()}><RefreshCw size={14}/> Refresh</button>}>
          <div className="table-toolbar"><div className="search-box"><Search size={15}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search by name, expression or run ID…"/></div><span className="muted small-text">{page==="saved"?filteredAlphas.length:history.length || 4} items</span></div>
          {page==="saved" ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Alpha</th><th>Status</th><th>Universe</th><th>Latest Sharpe</th><th>Updated</th><th/></tr></thead><tbody>{filteredAlphas.map(a=><tr key={a.id} className="clickable-row" onClick={()=>applyAlpha(a)}><td><strong>{a.name}</strong><small className="table-expression mono">{a.expression}</small></td><td><Status status={a.status}/></td><td>{a.universe}</td><td className="mono">{fmtNum(a.sharpe)}</td><td className="muted">{a.updated}</td><td><button className="btn btn-quiet" onClick={e=>{e.stopPropagation();applyAlpha(a);}}>Open <ChevronRight size={13}/></button></td></tr>)}</tbody></table></div>
          : <div className="table-scroll"><table className="data-table"><thead><tr><th>Run ID</th><th>Expression</th><th>Status</th><th>Created</th><th/></tr></thead><tbody>{(history.length?history:[{experiment_id:"demo-8fa2c1",status:"success",expression:demoExamples[0].expression,created_at:new Date().toISOString()},{experiment_id:"demo-7c20e4",status:"success",expression:demoExamples[2].expression,created_at:new Date(Date.now()-86400000).toISOString()}]).filter(r=>`${r.experiment_id} ${r.expression}`.toLowerCase().includes(search.toLowerCase())).map((r,i)=><tr key={r.experiment_id||i}><td className="mono">{r.experiment_id || r.run_id}</td><td><code className="table-expression">{r.expression || "Expression snapshot unavailable"}</code></td><td><Status status={r.status==="success"?"Succeeded":r.status}/></td><td className="muted">{r.created_at?new Date(r.created_at).toLocaleString():"—"}</td><td><button className="btn btn-quiet" onClick={()=>nav("results")}>Inspect <ChevronRight size={13}/></button></td></tr>)}</tbody></table></div>}
          <div className="table-foot"><span className="demo-inline">Preview mode stores drafts in memory for this browser session. Production persistence requires the Node API and Postgres layer.</span></div>
        </Panel>
        <Panel title="Compare completed runs" subtitle="Select two or more alphas to compare their latest preview metrics" action={<button className="btn btn-secondary" onClick={()=>notify("Comparison view is a preview; run snapshots should be compared via the production API.")}><GitCompare size={14}/> Compare selected ({selectedRuns.length})</button>}>
          <div className="compare-grid">{alphas.slice(0,4).map(a=><label className={`compare-card ${selectedRuns.includes(a.id)?"checked":""}`} key={a.id}><input type="checkbox" checked={selectedRuns.includes(a.id)} onChange={()=>toggleRun(a.id)}/><div><strong>{a.name}</strong><small className="mono">{a.id} · {a.universe}</small></div><span className="compare-sharpe">{fmtNum(a.sharpe)} <small>Sharpe</small></span></label>)}</div>
        </Panel>
      </section>}

      <div className="global-footer"><span>UNIFIED BACKTESTER <b>·</b> ALPHA RESEARCH</span><span><span className="footer-dot"/> {health==="connected"?"Connected to engine API":"Using local preview"} <b>·</b> v0.1.0</span></div>
    </main>
    {toast && <div className="toast"><CheckCircle2 size={16}/>{toast}<button onClick={()=>setToast("")}><X size={14}/></button></div>}
  </div>;
}

function FieldBrowser({ meta, insertField }) {
  const [term, setTerm] = useState("");
  const [group, setGroup] = useState("All");
  const native = meta?.fields?.native || ["open","high","low","close","volume"];
  const engineered = meta?.fields?.engineered || ["momentum_5","momentum_20","momentum_60","volatility_5","volatility_20","volatility_60","rsi_7","rsi_14","atr_14","sma_20","sma_50","sma_200","ema_9","ema_20","ema_50","macd","volume_ratio_20","volume_ratio_60"];
  const ops = meta?.operators?.map(o=>typeof o==="string"?o:o.name) || ["rank","zscore","normalize","ts_mean","ts_std_dev","ts_zscore","ts_delta","ts_rank","ts_corr","group_neutralize","group_rank","group_mean","sign","abs","log","sqrt","if_else"];
  const all = [...native.map(name=>({name,cat:"Native OHLCV"})),...engineered.map(name=>({name,cat:"Engineered"})),...ops.map(name=>({name,cat:"Operators"}))];
  const groups = ["All","Native OHLCV","Engineered","Operators"];
  const visible = all.filter(f=>(group==="All"||f.cat===group)&&f.name.toLowerCase().includes(term.toLowerCase()));
  return <div className="field-browser"><div className="search-box compact-search"><Search size={13}/><input value={term} onChange={e=>setTerm(e.target.value)} placeholder="Search fields and operators"/></div><div className="browser-groups">{groups.map(g=><button key={g} className={group===g?"active":""} onClick={()=>setGroup(g)}>{g}</button>)}</div><div className="field-list">{visible.slice(0,80).map(f=><button key={`${f.cat}-${f.name}`} onClick={()=>insertField(f.name)}><span className={`field-kind ${f.cat==="Operators"?"op":f.cat==="Engineered"?"eng":"native"}`}>{f.cat==="Operators"?"ƒ":f.cat==="Engineered"?"E":"D"}</span><code>{f.name}</code><Plus size={12}/></button>)}</div><div className="browser-note"><CircleHelp size={12}/> Manifest from API when connected; preview list otherwise.</div></div>;
}
