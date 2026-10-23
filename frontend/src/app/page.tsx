"use client";

import { useEffect, useState } from "react";
import { fetchMacroHistory, fetchMacroOverview, fetchUSMacroScore, type MacroHistory, type MacroHistoryPoint, type MacroOverview, type USMacroScore } from "@/lib/api";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  CircleDot,
  Clock3,
  Globe2,
  Layers3,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Wifi,
  WifiOff,
} from "lucide-react";

type HealthResponse = {
  status: string;
  project: string;
  phase: string;
};

type ServiceState = "checking" | "connected" | "offline";

const factorCards = [
  {
    code: "GLB",
    title: "Global economy",
    description: "Growth, inflation and global liquidity",
    icon: Globe2,
  },
  {
    code: "IND",
    title: "Indian economy",
    description: "Domestic growth, rates and credit",
    icon: BarChart3,
  },
  {
    code: "GEO",
    title: "Geopolitical risk",
    description: "Conflict, trade and policy uncertainty",
    icon: ShieldAlert,
  },
  {
    code: "MKT",
    title: "Market conditions",
    description: "Trend, breadth and volatility",
    icon: Activity,
  },
  {
    code: "FXC",
    title: "FX & commodities",
    description: "Currency, energy and key inputs",
    icon: Layers3,
  },
];

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function Sparkline({ points }: { points: MacroHistoryPoint[] }) {
  if (points.length < 2) {
    return <p className="py-3 text-[10px] text-muted">Not enough historical points to chart.</p>;
  }

  const values = points.map((point) => point.value);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const span = maxValue - minValue || 1;
  const coordinates = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * 100;
      const y = 30 - ((point.value - minValue) / span) * 24;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <div className="mt-4 rounded-lg border border-line bg-panel/50 px-3 py-2">
      <div className="mb-2 flex items-center justify-between gap-2 text-[10px] text-muted">
        <span>Recent history</span>
        <span>{points.length} observations</span>
      </div>
      <svg
        viewBox="0 0 100 36"
        role="img"
        aria-label={`Historical trend across ${points.length} observations`}
        className="h-10 w-full overflow-visible text-accent"
        preserveAspectRatio="none"
      >
        <polyline
          points={coordinates}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div className="mt-1 flex justify-between text-[9px] text-muted">
        <span>{points[0].observation_date}</span>
        <span>{points[points.length - 1].observation_date}</span>
      </div>
    </div>
  );
}

export default function Home() {
  const [serviceState, setServiceState] = useState<ServiceState>("checking");
  const [checkedAt, setCheckedAt] = useState<string>("—");
  const [retry, setRetry] = useState(0);
  const [macroOverview, setMacroOverview] = useState<MacroOverview | null>(null);
  const [historyByKey, setHistoryByKey] = useState<Record<string, MacroHistory | null>>({});
  const [macroLoading, setMacroLoading] = useState(true);
  const [macroError, setMacroError] = useState<string | null>(null);
  const [usScore, setUsScore] = useState<USMacroScore | null>(null);
  const [scoreLoading, setScoreLoading] = useState(true);
  const [scoreError, setScoreError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setMacroLoading(true);
    setMacroError(null);
    const baseUrl = (
      process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
    ).replace(/\/$/, "");

    fetchMacroOverview(controller.signal)
      .then(async (data) => {
        if (!active) return;
        setMacroOverview(data);
        setMacroError(null);
        setMacroLoading(false);

        const entries = await Promise.all(
          data.indicators.map(async (item) => {
            if (item.status !== "available") return [item.key, null] as const;
            try {
              const history = await fetchMacroHistory(item.key, 12, controller.signal);
              return [item.key, history] as const;
            } catch {
              return [item.key, null] as const;
            }
          }),
        );
        if (active) setHistoryByKey(Object.fromEntries(entries));
      })
      .catch((error: unknown) => {
        if (!active) return;
        setMacroError(
          error instanceof Error ? error.message : "Unable to load macro data.",
        );
      })
      .finally(() => {
        if (active) setMacroLoading(false);
      });

    setScoreLoading(true);
    setScoreError(null);
    fetchUSMacroScore(controller.signal)
      .then((data) => {
        if (!active) return;
        setUsScore(data);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setScoreError(
          error instanceof Error ? error.message : "Unable to load the U.S. macro score.",
        );
      })
      .finally(() => {
        if (active) setScoreLoading(false);
      });

    fetch(`${baseUrl}/health`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("API health check failed");
        return response.json() as Promise<HealthResponse>;
      })
      .then((data) => {
        if (!active) return;
        setServiceState(data.status === "ok" ? "connected" : "offline");
        setCheckedAt(formatTime(new Date()));
      })
      .catch(() => {
        if (!active) return;
        setServiceState("offline");
        setCheckedAt(formatTime(new Date()));
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [retry]);

  return (
    <main className="min-h-screen px-4 pb-10 pt-5 sm:px-7 lg:px-10">
      <div className="mx-auto max-w-[1440px]">
        <header className="flex flex-wrap items-center justify-between gap-5 border-b border-line pb-5">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl border border-accent/30 bg-accent/10 text-accent">
              <Activity size={21} strokeWidth={1.8} />
            </div>
            <div>
              <div className="text-lg font-semibold tracking-[0.18em] text-white">ARTHVEST</div>
              <div className="mt-0.5 text-[10px] uppercase tracking-[0.24em] text-muted">Macro intelligence</div>
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs text-muted">
            <span className="hidden sm:inline">PHASE 01 / FOUNDATION</span>
            <span className="h-4 w-px bg-line" />
            <span className="flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-2">
              {serviceState === "connected" ? (
                <Wifi size={13} className="text-accent" />
              ) : serviceState === "offline" ? (
                <WifiOff size={13} className="text-amber-300" />
              ) : (
                <RefreshCw size={13} className="animate-spin text-muted" />
              )}
              <span className={serviceState === "connected" ? "text-accent" : serviceState === "offline" ? "text-amber-300" : "text-muted"}>
                {serviceState === "connected" ? "API CONNECTED" : serviceState === "offline" ? "API OFFLINE" : "CONNECTING"}
              </span>
            </span>
          </div>
        </header>

        <section className="grid gap-8 py-9 lg:grid-cols-[1.3fr_0.7fr] lg:items-end lg:py-12">
          <div>
            <div className="mb-4 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.2em] text-accent">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              A clearer view of the macro landscape
            </div>
            <h1 className="max-w-3xl text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl lg:text-6xl">
              Read the <span className="text-accent">macro.</span>
              <br />Understand the regime.
            </h1>
            <p className="mt-5 max-w-2xl text-sm leading-7 text-muted sm:text-base">
              A research-first terminal for global liquidity, India&apos;s economic pulse, geopolitical risk and market conditions — built around transparent data and explainable signals.
            </p>
          </div>
          <div className="rounded-2xl border border-line bg-panel/80 p-5 sm:p-6">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-muted">
                <Clock3 size={14} /> System status
              </div>
              <span className="rounded-md border border-line px-2 py-1 text-[10px] text-muted">LOCAL DEV</span>
            </div>
            <div className="mt-5 flex items-end justify-between gap-3">
              <div>
                <div className="text-2xl font-semibold text-white">
                  {serviceState === "connected" ? "Operational" : serviceState === "offline" ? "Awaiting API" : "Checking…"}
                </div>
                <div className="mt-1 text-xs text-muted">Last check: {checkedAt}</div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setServiceState("checking");
                  setRetry((value) => value + 1);
                }}
                className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-slate-200 transition hover:border-accent/50 hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent/50"
              >
                <RefreshCw size={13} /> Retry
              </button>
            </div>
            <div className="mt-5 h-1 overflow-hidden rounded-full bg-line">
              <div className={`h-full rounded-full transition-all ${serviceState === "connected" ? "w-full bg-accent" : serviceState === "offline" ? "w-1/4 bg-amber-300" : "w-1/2 animate-pulse bg-muted"}`} />
            </div>
          </div>
        </section>

        <section aria-labelledby="regime-title" className="overflow-hidden rounded-2xl border border-line bg-panel/70">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-5 py-5 sm:px-7">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-muted">Macro regime monitor</div>
              <h2 id="regime-title" className="mt-2 text-xl font-medium text-white sm:text-2xl">Investment readiness</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">The full global and India composite remains inactive. A separate provisional U.S. conditions subscore is shown below and must not be interpreted as the full Arthvest regime.</p>
            </div>
            <span className="rounded-full border border-amber-300/25 bg-amber-300/5 px-3 py-1.5 text-[10px] uppercase tracking-[0.13em] text-amber-200">Model not calibrated</span>
          </div>

          <div className="grid gap-0 md:grid-cols-[0.8fr_1.2fr]">
            <div className="border-b border-line p-5 sm:p-7 md:border-b-0 md:border-r">
              <div className="text-xs text-muted">Composite score</div>
              <div className="mt-4 flex items-baseline gap-3">
                <span className="text-6xl font-light tracking-tight text-white">—</span>
                <span className="text-sm text-muted">/ 100</span>
              </div>
              <div className="mt-5 flex items-center gap-2 text-xs text-muted"><CircleDot size={14} /> No score published</div>
              <div className="mt-7 grid grid-cols-3 gap-2">
                {[
                  { label: "Risk appetite", value: "Pending" },
                  { label: "Data coverage", value: "0 / 5" },
                  { label: "Signal quality", value: "Pending" },
                ].map((item) => (
                  <div key={item.label} className="rounded-xl border border-line bg-[#0B1017] p-3">
                    <div className="text-[10px] leading-4 text-muted">{item.label}</div>
                    <div className="mt-2 text-xs font-medium text-slate-200">{item.value}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="p-5 sm:p-7">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="text-xs font-medium text-slate-200">Five-factor framework</div>
                <div className="text-[10px] uppercase tracking-[0.14em] text-muted">Awaiting data</div>
              </div>
              <div className="space-y-2">
                {factorCards.map((factor) => {
                  const Icon = factor.icon;
                  return (
                    <div key={factor.code} className="group flex items-center gap-3 rounded-xl border border-line/80 bg-[#0B1017]/70 p-3 transition hover:border-slate-600 sm:gap-4 sm:p-4">
                      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line bg-panel text-muted transition group-hover:text-accent"><Icon size={16} /></div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium text-slate-200">{factor.title}</span>
                          <span className="text-[9px] tracking-[0.12em] text-muted">{factor.code}</span>
                        </div>
                        <div className="mt-1 text-xs text-muted">{factor.description}</div>
                      </div>
                      <span className="shrink-0 rounded-md border border-line px-2 py-1 text-[9px] uppercase tracking-[0.1em] text-muted">Pending</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </section>

        <section
          aria-labelledby="us-score-title"
          className="mt-6 overflow-hidden rounded-2xl border border-line bg-panel/70"
        >
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-5 py-5 sm:px-7">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent">Experimental model / U.S. only</div>
              <h2 id="us-score-title" className="mt-2 text-xl font-medium text-white">
                U.S. macro conditions subscore
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
                A transparent rules-based prototype using policy rates, CPI inflation and unemployment. It is not a market forecast or the complete Arthvest global/India score.
              </p>
            </div>
            <span className="rounded-full border border-amber-300/25 bg-amber-300/5 px-3 py-1.5 text-[10px] uppercase tracking-[0.12em] text-amber-200">
              Provisional · not calibrated
            </span>
          </div>

          <div className="p-5 sm:p-7">
            {scoreLoading ? (
              <div role="status" className="flex items-center gap-3 py-5 text-sm text-muted">
                <RefreshCw size={16} className="animate-spin" /> Calculating from validated observations…
              </div>
            ) : scoreError ? (
              <div role="status" className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm leading-6 text-amber-200">{scoreError}</p>
                <button
                  type="button"
                  onClick={() => {
                    setScoreLoading(true);
                    setRetry((value) => value + 1);
                  }}
                  className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-slate-200 transition hover:border-accent/50 hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent/50"
                >
                  <RefreshCw size={13} /> Retry score
                </button>
              </div>
            ) : usScore?.available && usScore.score !== null ? (
              <>
                <div className="grid gap-5 md:grid-cols-[0.65fr_1.35fr]">
                  <div className="rounded-xl border border-line bg-[#0B1017] p-5">
                    <div className="text-xs text-muted">U.S. conditions score</div>
                    <div className="mt-3 flex items-baseline gap-2">
                      <span className="text-6xl font-light tracking-tight text-white">{usScore.score.toFixed(1)}</span>
                      <span className="text-sm text-muted">/ 100</span>
                    </div>
                    <div className="mt-3 inline-flex rounded-md border border-line px-2.5 py-1.5 text-xs uppercase tracking-[0.12em] text-slate-200">
                      {usScore.label}
                    </div>
                    <p className="mt-4 text-xs leading-5 text-muted">
                      Calculated {new Date(usScore.generated_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                    </p>
                  </div>

                  <div className="space-y-3">
                    {usScore.components.map((component) => (
                      <div key={component.key} className="rounded-xl border border-line bg-[#0B1017] p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-white">{component.indicator}</div>
                            <div className="mt-1 text-[10px] text-muted">
                              {component.observation_date ? `Observation ${component.observation_date}` : "Observation unavailable"}
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="text-sm font-medium text-slate-100">
                              {component.value_percent === null ? "—" : `${component.value_percent.toFixed(2)}%`}
                            </div>
                            <div className="mt-1 text-[10px] text-muted">
                              Weight {(component.weight * 100).toFixed(0)}%
                            </div>
                          </div>
                        </div>
                        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-line">
                          <div
                            className="h-full rounded-full bg-accent"
                            style={{ width: `${component.component_score ?? 0}%` }}
                          />
                        </div>
                        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[10px] text-muted">
                          <span>Component score: {component.component_score === null ? "not scored" : component.component_score.toFixed(0) + " / 100"}</span>
                          <span>Contribution: {component.weighted_points === null ? "—" : component.weighted_points.toFixed(1) + " points"}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <details className="mt-5 rounded-xl border border-line px-4 py-3">
                  <summary className="cursor-pointer text-xs font-medium text-slate-200">Scoring methodology & limitations</summary>
                  <p className="mt-3 text-xs leading-6 text-muted">{usScore.methodology}</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-muted">
                    {usScore.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
                  </ul>
                </details>
              </>
            ) : (
              <div role="status" className="rounded-xl border border-amber-300/20 bg-amber-300/[0.03] p-5">
                <div className="text-base font-medium text-amber-100">Score withheld — insufficient fresh data</div>
                <p className="mt-2 text-sm leading-6 text-muted">
                  Arthvest will not fill gaps with made-up values or calculate a partial score when required inputs are missing or stale.
                </p>
                {usScore?.blockers?.length ? (
                  <ul className="mt-3 list-disc space-y-1 pl-5 text-xs leading-5 text-muted">
                    {usScore.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
                  </ul>
                ) : null}
                {usScore?.methodology ? (
                  <p className="mt-3 text-xs leading-5 text-muted">{usScore.methodology}</p>
                ) : null}
              </div>
            )}
          </div>
        </section>

        <section
          aria-labelledby="macro-observation-title"
          className="mt-6 overflow-hidden rounded-2xl border border-line bg-panel/70"
        >
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-5 py-5 sm:px-7">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent">Data connections / 01</div>
              <h2 id="macro-observation-title" className="mt-2 text-xl font-medium text-white">
                Macro indicator board
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
                Source-attributed U.S. indicators to establish the first working data pipeline. Each card shows the source observation date, not a real-time market quote.
              </p>
            </div>
            <span className="rounded-full border border-line px-3 py-1.5 text-[10px] uppercase tracking-[0.12em] text-muted">
              {macroOverview
                ? `${macroOverview.available_count} / ${macroOverview.total_count} available`
                : "Loading sources"}
            </span>
          </div>

          <div className="p-5 sm:p-7">
            {macroLoading ? (
              <div role="status" className="flex items-center gap-3 py-5 text-sm text-muted">
                <RefreshCw size={16} className="animate-spin" />
                Fetching macro observations…
              </div>
            ) : macroError ? (
              <div role="status" className="flex flex-col items-start gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="max-w-2xl text-sm leading-6 text-amber-200">{macroError}</p>
                <button
                  type="button"
                  onClick={() => {
                    setMacroLoading(true);
                    setRetry((value) => value + 1);
                  }}
                  className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-slate-200 transition hover:border-accent/50 hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent/50"
                >
                  <RefreshCw size={13} /> Retry data
                </button>
              </div>
            ) : macroOverview ? (
              <div className="grid gap-4 lg:grid-cols-3">
                {macroOverview.indicators.map((item) => (
                  <article
                    key={item.key}
                    className="flex min-h-[260px] flex-col rounded-xl border border-line bg-[#0B1017] p-4 sm:p-5"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <span className="text-[10px] uppercase tracking-[0.14em] text-muted">{item.category}</span>
                      <span
                        className={`shrink-0 rounded-full border px-2 py-1 text-[9px] uppercase tracking-[0.1em] ${
                          item.status === "available" && item.data?.freshness_status === "fresh"
                            ? "border-accent/25 bg-accent/5 text-accent"
                            : "border-amber-300/25 bg-amber-300/5 text-amber-200"
                        }`}
                      >
                        {item.status === "unavailable"
                          ? "unavailable"
                          : item.data?.freshness_status ?? "unknown"}
                      </span>
                    </div>

                    <h3 className="mt-4 min-h-10 text-sm font-medium leading-5 text-white">
                      {item.data?.indicator ?? item.key}
                    </h3>

                    {item.data ? (
                      <>
                        <div className="mt-3 flex items-baseline gap-2">
                          <span className="text-4xl font-light tracking-tight text-white">
                            {item.data.value.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}
                          </span>
                          <span className="max-w-[120px] break-words text-xs leading-4 text-accent">{item.data.unit.startsWith("percent") ? "%" : item.data.unit}</span>
                        </div>
                        <div className="mt-4 border-t border-line pt-3">
                          <div className="text-[10px] uppercase tracking-[0.12em] text-muted">Observation date</div>
                          <div className="mt-1 text-xs font-medium text-slate-200">
                            {new Date(item.data.observation_date + "T00:00:00").toLocaleDateString("en-IN", {
                              day: "2-digit",
                              month: "short",
                              year: "numeric",
                            })}
                          </div>
                          <div className="mt-1 text-[10px] text-muted">
                            {item.data.observation_age_days} calendar days since observation
                          </div>
                        </div>
                        {item.data.calculation ? (
                          <p className="mt-3 text-[11px] leading-5 text-muted">{item.data.calculation}</p>
                        ) : null}
                        {historyByKey[item.key] ? (
                          <Sparkline points={historyByKey[item.key]!.points} />
                        ) : (
                          <div className="mt-4 rounded-lg border border-line/60 px-3 py-2 text-[10px] text-muted">
                            Historical trend currently unavailable.
                          </div>
                        )}
                        <div className="mt-auto pt-4">
                          <a
                            href={item.data.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1.5 text-xs text-slate-300 underline decoration-line underline-offset-4 transition hover:text-accent"
                          >
                            {item.data.source} <ArrowUpRight size={12} />
                          </a>
                          <div className="mt-2 text-[10px] text-muted">
                            {item.data.series_id} · Retrieved {new Date(item.data.retrieved_at).toLocaleString("en-IN", {
                              dateStyle: "medium",
                              timeStyle: "short",
                            })}
                          </div>
                        </div>
                      </>
                    ) : (
                      <div className="mt-4 rounded-lg border border-line px-3 py-4">
                        <div className="text-lg font-light text-amber-200">Unavailable</div>
                        <p className="mt-2 text-xs leading-5 text-muted">
                          {item.error ?? "No validated source observation is available."}
                        </p>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <p className="py-4 text-sm text-muted">No macro overview is available.</p>
            )}

            {macroOverview ? (
              <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4 text-[10px] text-muted">
                <span>Partial source failures do not hide the other indicators.</span>
                <span>Snapshot generated {new Date(macroOverview.generated_at).toLocaleString("en-IN", {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}</span>
              </div>
            ) : null}
          </div>
        </section>

        <section className="mt-6 grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-line bg-panel/50 p-5">
            <div className="flex items-center justify-between text-muted"><span className="text-xs">Data provenance</span><CheckCircle2 size={16} className="text-accent" /></div>
            <div className="mt-4 text-base font-medium text-white">Source-first design</div>
            <p className="mt-2 text-xs leading-6 text-muted">Every live reading will carry its source, observation date and retrieval timestamp.</p>
          </div>
          <div className="rounded-2xl border border-line bg-panel/50 p-5">
            <div className="flex items-center justify-between text-muted"><span className="text-xs">Analysis approach</span><Sparkles size={16} className="text-accent" /></div>
            <div className="mt-4 text-base font-medium text-white">Explainable signals</div>
            <p className="mt-2 text-xs leading-6 text-muted">Deterministic rules first. Initial weights and thresholds remain provisional until tested.</p>
          </div>
          <div className="rounded-2xl border border-line bg-panel/50 p-5">
            <div className="flex items-center justify-between text-muted"><span className="text-xs">Risk discipline</span><ArrowUpRight size={16} className="text-accent" /></div>
            <div className="mt-4 text-base font-medium text-white">No fabricated readings</div>
            <p className="mt-2 text-xs leading-6 text-muted">Unavailable or stale data will be identified explicitly rather than silently replaced.</p>
          </div>
        </section>

        <footer className="mt-8 flex flex-col gap-3 border-t border-line pt-5 text-[10px] leading-5 text-muted sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2"><Activity size={12} /> ARTHVEST <span className="text-line">/</span> MACRO INTELLIGENCE</div>
          <div className="flex items-center gap-2"><ArrowDownRight size={12} /> Research and decision support, not personalized financial advice.</div>
        </footer>
      </div>
    </main>
  );
}
