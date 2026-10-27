import Link from "next/link";
"use client";

import { useEffect, useState } from "react";
import { fetchHistoricalAnalytics, fetchMacroCatalog, fetchMacroComparison, fetchMacroHistory, fetchMacroOverview, fetchMacroQuality, fetchMacroRevisions, fetchMacroSourceChecks, fetchMacroStorageStatus, fetchUSMacroScore, type HistoricalAnalytics, type MacroCatalog, type MacroComparison, type MacroHistory, type MacroHistoryPoint, type MacroOverview, type MacroQuality, type MacroRevisions, type MacroSourceChecks, type MacroStorageStatus, type USMacroScore } from "@/lib/api";
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
  Database,
  Minus,
  TrendingDown,
  TrendingUp,
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


const comparisonOptions = [
  { key: "fed-funds", label: "Federal Funds Rate" },
  { key: "us-inflation", label: "U.S. CPI inflation YoY" },
  { key: "us-unemployment", label: "U.S. unemployment" },
  { key: "india-gdp-growth", label: "India real GDP growth" },
  { key: "india-cpi-inflation-annual", label: "India annual CPI inflation" },
  { key: "india-policy-uncertainty", label: "India policy uncertainty" },
  { key: "usd-inr", label: "INR per USD" },
  { key: "india-reer", label: "India REER" },
];

const factorCards = [
  {
    code: "GLB",
    title: "Global economy",
    description: "Current feed covers U.S. rates, inflation and employment only",
    indicatorKeys: ["fed-funds", "us-inflation", "us-unemployment"],
    scopeLabel: "U.S.-only coverage",
    connected: true,
    icon: Globe2,
  },
  {
    code: "IND",
    title: "Indian economy",
    description: "GDP growth, annual inflation and policy uncertainty",
    indicatorKeys: ["india-gdp-growth", "india-cpi-inflation-annual", "india-policy-uncertainty"],
    scopeLabel: "Partial coverage",
    connected: true,
    icon: BarChart3,
  },
  {
    code: "GEO",
    title: "Geopolitical risk",
    description: "Conflict, trade and policy uncertainty signals",
    indicatorKeys: [],
    scopeLabel: "Not connected",
    connected: false,
    icon: ShieldAlert,
  },
  {
    code: "MKT",
    title: "Market conditions",
    description: "Market trend, breadth and volatility feeds",
    indicatorKeys: [],
    scopeLabel: "Not connected",
    connected: false,
    icon: Activity,
  },
  {
    code: "FXC",
    title: "FX & commodities",
    description: "INR/USD and real effective exchange rate; commodity feeds not yet added",
    indicatorKeys: ["usd-inr", "india-reer"],
    scopeLabel: "Partial coverage",
    connected: true,
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

function formatObservationPeriod(observationDate: string, frequency: string): string {
  const date = new Date(observationDate + "T00:00:00");
  const year = date.getFullYear();

  if (frequency === "Annual") return String(year);
  if (frequency === "Quarterly") {
    return `Q${Math.floor(date.getMonth() / 3) + 1} ${year}`;
  }
  if (frequency === "Monthly") {
    return date.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
  }
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function Sparkline({
  points,
  frequency,
}: {
  points: MacroHistoryPoint[];
  frequency: string;
}) {
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
        <span>{formatObservationPeriod(points[0].observation_date, frequency)}</span>
        <span>{formatObservationPeriod(points[points.length - 1].observation_date, frequency)}</span>
      </div>
    </div>
  );
}


function ComparisonPlot({ comparison }: { comparison: MacroComparison }) {
  const usableSeries = comparison.series.filter(
    (series) => series.status === "available" && series.points.length >= 2,
  );
  if (usableSeries.length === 0) return null;

  const allValues = usableSeries.flatMap((series) =>
    series.points.map((point) => point.indexed_value),
  );
  const minValue = Math.min(...allValues);
  const maxValue = Math.max(...allValues);
  const span = maxValue - minValue || 1;
  const startMs = new Date(comparison.window_start + "T00:00:00Z").getTime();
  const endMs = new Date(comparison.window_end + "T00:00:00Z").getTime();
  const colors = ["#7dd3fc", "#c4b5fd", "#fbbf24", "#86efac", "#fda4af"];

  return (
    <div className="mt-5 rounded-xl border border-line bg-[#0B1017] p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium text-white">Relative trend · base = 100</div>
          <p className="mt-1 text-[10px] leading-5 text-muted">
            Indexed values are relative to each series&apos; first observation in the window.
          </p>
        </div>
        <div className="text-[10px] text-muted">A higher index means the indicator&apos;s value increased.</div>
      </div>
      <svg viewBox="0 0 820 120" role="img" aria-label="Normalized historical comparison chart" className="mt-4 h-44 w-full overflow-visible">
        {[20, 40, 60, 80, 100].map((y) => (
          <line key={y} x1="10" x2="810" y1={y} y2={y} stroke="#26313f" strokeWidth="1" />
        ))}
        {usableSeries.map((series, index) => {
          const coords = series.points.map((point) => {
            const observedMs = new Date(point.observation_date + "T00:00:00Z").getTime();
            const x = endMs > startMs
              ? 10 + (Math.min(1, Math.max(0, (observedMs - startMs) / (endMs - startMs))) * 800)
              : 10;
            const y = 104 - ((point.indexed_value - minValue) / span) * 88;
            return x.toFixed(2) + "," + y.toFixed(2);
          }).join(" ");
          return (
            <polyline
              key={series.key}
              points={coords}
              fill="none"
              stroke={colors[index % colors.length]}
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
        {usableSeries.map((series) => {
          const color = colors[usableSeries.findIndex((item) => item.key === series.key) % colors.length];
          return (
            <div key={series.key} className="flex items-center gap-2 text-[10px] text-slate-300">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
              <span>{series.indicator}</span>
            </div>
          );
        })}
      </div>
      <div className="mt-3 flex justify-between text-[9px] text-muted">
        <span>{new Date(comparison.window_start + "T00:00:00").toLocaleDateString("en-IN", { month: "short", year: "numeric" })}</span>
        <span>{new Date(comparison.window_end + "T00:00:00").toLocaleDateString("en-IN", { month: "short", year: "numeric" })}</span>
      </div>
    </div>
  );
}

function MacroDelta({
  history,
  unit,
}: {
  history: MacroHistory | null | undefined;
  unit: string;
}) {
  if (!history || history.points.length < 2) return null;

  const current = history.points[history.points.length - 1].value;
  const previous = history.points[history.points.length - 2].value;
  const delta = current - previous;
  const unitLabel = unit.startsWith("percent")
    ? "pp"
    : unit.toLowerCase().startsWith("index")
      ? "index pts"
      : unit === "INR per USD"
        ? "INR/USD"
        : unit;

  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[10px] text-muted">
      <span>Change vs previous observation</span>
      <span className="font-medium text-slate-300">
        {delta > 0 ? "+" : ""}{delta.toFixed(2)} {unitLabel}
      </span>
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
  const [macroQuality, setMacroQuality] = useState<MacroQuality | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);
  const [macroCatalog, setMacroCatalog] = useState<MacroCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [usScore, setUsScore] = useState<USMacroScore | null>(null);
  const [scoreLoading, setScoreLoading] = useState(true);
  const [scoreError, setScoreError] = useState<string | null>(null);
  const [analyticsKey, setAnalyticsKey] = useState("fed-funds");
  const [historicalAnalytics, setHistoricalAnalytics] = useState<HistoricalAnalytics | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(true);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [analyticsRetry, setAnalyticsRetry] = useState(0);
  const [comparisonKeys, setComparisonKeys] = useState<string[]>([
    "fed-funds", "us-inflation", "us-unemployment",
  ]);
  const [comparisonYears, setComparisonYears] = useState(5);
  const [comparison, setComparison] = useState<MacroComparison | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(true);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [comparisonRetry, setComparisonRetry] = useState(0);
  const [storageStatus, setStorageStatus] = useState<MacroStorageStatus | null>(null);
  const [sourceChecks, setSourceChecks] = useState<MacroSourceChecks | null>(null);
  const [archiveLoading, setArchiveLoading] = useState(true);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [archiveRetry, setArchiveRetry] = useState(0);
  const [revisionKey, setRevisionKey] = useState("fed-funds");
  const [revisionData, setRevisionData] = useState<MacroRevisions | null>(null);
  const [revisionLoading, setRevisionLoading] = useState(true);
  const [revisionError, setRevisionError] = useState<string | null>(null);
  const [revisionRetry, setRevisionRetry] = useState(0);

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

        try {
          const quality = await fetchMacroQuality(controller.signal);
          if (active) {
            setMacroQuality(quality);
            setQualityError(null);
          }
        } catch (error: unknown) {
          if (active) {
            setQualityError(
              error instanceof Error ? error.message : "Unable to load data quality.",
            );
          }
        }

        try {
          const catalog = await fetchMacroCatalog(controller.signal);
          if (active) {
            setMacroCatalog(catalog);
            setCatalogError(null);
          }
        } catch (error: unknown) {
          if (active) {
            setCatalogError(
              error instanceof Error ? error.message : "Unable to load the indicator catalog.",
            );
          }
        }

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

  useEffect(() => {
    const controller = new AbortController();
    setAnalyticsLoading(true);
    setAnalyticsError(null);
    setHistoricalAnalytics(null);

    fetchHistoricalAnalytics(analyticsKey, 12, controller.signal)
      .then((result) => {
        setHistoricalAnalytics(result);
        setAnalyticsError(null);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setHistoricalAnalytics(null);
        setAnalyticsError(
          error instanceof Error ? error.message : "Unable to load archived historical analytics.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setAnalyticsLoading(false);
      });

    return () => controller.abort();
  }, [analyticsKey, analyticsRetry]);

  useEffect(() => {
    const controller = new AbortController();
    setComparisonLoading(true);
    setComparisonError(null);
    setComparison(null);

    fetchMacroComparison(comparisonKeys, comparisonYears, controller.signal)
      .then((result) => {
        setComparison(result);
        setComparisonError(null);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setComparison(null);
        setComparisonError(
          error instanceof Error ? error.message : "Unable to compare archived macro indicators.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setComparisonLoading(false);
      });

    return () => controller.abort();
  }, [comparisonKeys, comparisonYears, comparisonRetry]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setArchiveLoading(true);
    setArchiveError(null);

    fetchMacroStorageStatus(controller.signal)
      .then(async (status) => {
        if (!active) return;
        setStorageStatus(status);
        setSourceChecks(null);
        if (!status.enabled || !status.available) return;
        try {
          const result = await fetchMacroSourceChecks(12, controller.signal);
          if (active) setSourceChecks(result);
        } catch (error: unknown) {
          if (active) {
            setArchiveError(
              error instanceof Error ? error.message : "Unable to load recent source checks.",
            );
          }
        }
      })
      .catch((error: unknown) => {
        if (!active) return;
        setStorageStatus(null);
        setArchiveError(
          error instanceof Error ? error.message : "Unable to load database status.",
        );
      })
      .finally(() => {
        if (active) setArchiveLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [archiveRetry]);

  useEffect(() => {
    const controller = new AbortController();
    setRevisionLoading(true);
    setRevisionError(null);
    setRevisionData(null);

    fetchMacroRevisions(revisionKey, 20, controller.signal)
      .then((result) => {
        setRevisionData(result);
        setRevisionError(null);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setRevisionData(null);
        setRevisionError(
          error instanceof Error ? error.message : "Unable to load source revision history.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setRevisionLoading(false);
      });

    return () => controller.abort();
  }, [revisionKey, revisionRetry]);

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
            <Link href="/markets" className="rounded-lg border border-accent/25 bg-accent/5 px-3 py-2 text-accent transition hover:border-accent/50">MARKET PULSE ↗</Link>
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
                  const matchingIndicators = macroOverview
                    ? macroOverview.indicators.filter((item) => factor.indicatorKeys.includes(item.key))
                    : [];
                  const freshCount = matchingIndicators.filter(
                    (item) => item.status === "available" && item.data?.freshness_status === "fresh",
                  ).length;
                  const availabilityLabel = !factor.connected
                    ? "Not connected"
                    : !macroOverview
                      ? "Checking data"
                      : `${freshCount}/${factor.indicatorKeys.length} fresh`;
                  return (
                    <div key={factor.code} className="group flex items-center gap-3 rounded-xl border border-line/80 bg-[#0B1017]/70 p-3 transition hover:border-slate-600 sm:gap-4 sm:p-4">
                      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line bg-panel text-muted transition group-hover:text-accent"><Icon size={16} /></div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium text-slate-200">{factor.title}</span>
                          <span className="text-[9px] tracking-[0.12em] text-muted">{factor.code}</span>
                          <span className="rounded border border-line px-1.5 py-0.5 text-[8px] uppercase tracking-[0.08em] text-muted">{factor.scopeLabel}</span>
                        </div>
                        <div className="mt-1 text-xs leading-5 text-muted">{factor.description}</div>
                      </div>
                      <span className={`shrink-0 rounded-md border px-2 py-1 text-[9px] uppercase tracking-[0.1em] ${
                        !factor.connected
                          ? "border-amber-300/25 bg-amber-300/5 text-amber-200"
                          : macroOverview && freshCount === factor.indicatorKeys.length
                            ? "border-accent/25 bg-accent/5 text-accent"
                            : "border-line text-muted"
                      }`}>{availabilityLabel}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </section>



        <section
          aria-labelledby="archive-health-title"
          className="mt-6 overflow-hidden rounded-2xl border border-line bg-panel/70"
        >
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-5 py-5 sm:px-7">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent">Infrastructure / data integrity</div>
              <h2 id="archive-health-title" className="mt-2 text-xl font-medium text-white">
                Archive health
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
                Verify whether persistent storage is enabled and reachable, how much source history has been retained, and whether recent upstream fetches succeeded.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setArchiveRetry((value) => value + 1)}
              className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-slate-200 transition hover:border-accent/50 hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent/50"
            >
              <RefreshCw size={13} /> Refresh archive status
            </button>
          </div>
          <div className="p-5 sm:p-7">
            {archiveLoading ? (
              <div role="status" className="flex items-center gap-3 py-5 text-sm text-muted">
                <RefreshCw size={16} className="animate-spin" /> Checking database and source history…
              </div>
            ) : archiveError && !storageStatus ? (
              <div role="status" className="rounded-xl border border-amber-300/20 bg-amber-300/[0.03] p-4 text-sm text-amber-100">
                {archiveError}
              </div>
            ) : storageStatus ? (
              <>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className={"grid h-10 w-10 shrink-0 place-items-center rounded-xl border " +
                      (storageStatus.available ? "border-accent/30 bg-accent/10 text-accent" : "border-amber-300/25 bg-amber-300/5 text-amber-200")}>
                      <Database size={18} />
                    </div>
                    <div>
                      <div className="text-sm font-medium text-white">
                        {!storageStatus.enabled
                          ? "Persistence disabled"
                          : storageStatus.available
                            ? "Database connected"
                            : "Database unreachable"}
                      </div>
                      <p className="mt-1 max-w-3xl text-xs leading-5 text-muted">{storageStatus.note}</p>
                    </div>
                  </div>
                  <span className={"rounded-full border px-3 py-1.5 text-[10px] uppercase tracking-[0.1em] " +
                    (!storageStatus.enabled
                      ? "border-amber-300/25 bg-amber-300/5 text-amber-200"
                      : storageStatus.available
                        ? "border-accent/25 bg-accent/5 text-accent"
                        : "border-amber-300/25 bg-amber-300/5 text-amber-200")}>
                    {!storageStatus.enabled ? "Not configured" : storageStatus.available ? storageStatus.backend + " · online" : "Connection error"}
                  </span>
                </div>

                <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  {[
                    { label: "Archived observations", value: storageStatus.observation_count },
                    { label: "Detected revisions", value: storageStatus.revision_count },
                    { label: "Recorded source checks", value: storageStatus.source_check_count },
                    {
                      label: "Last source check",
                      value: storageStatus.last_check_at
                        ? new Date(storageStatus.last_check_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })
                        : null,
                    },
                  ].map((metric) => (
                    <div key={metric.label} className="rounded-xl border border-line bg-[#0B1017] p-4">
                      <div className="text-[10px] text-muted">{metric.label}</div>
                      <div className="mt-2 break-words text-lg font-light text-white">
                        {metric.value === null ? "—" : typeof metric.value === "number" ? metric.value.toLocaleString("en-US") : metric.value}
                      </div>
                    </div>
                  ))}
                </div>

                {archiveError ? (
                  <p role="status" className="mt-4 text-xs leading-5 text-amber-200">{archiveError}</p>
                ) : null}

                {storageStatus.enabled && storageStatus.available ? (
                  <div className="mt-5 overflow-hidden rounded-xl border border-line">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
                      <div className="text-xs font-medium text-slate-200">Recent upstream fetch checks</div>
                      <div className="text-[10px] text-muted">
                        {sourceChecks ? sourceChecks.count + " checks returned" : "No checks loaded"}
                      </div>
                    </div>
                    {sourceChecks && sourceChecks.checks.length > 0 ? (
                      <div className="divide-y divide-line">
                        {sourceChecks.checks.slice(0, 8).map((check, index) => (
                          <div key={check.series_id + "-" + check.checked_at + "-" + index} className="flex flex-wrap items-center gap-3 px-4 py-3">
                            <span className={"h-2 w-2 shrink-0 rounded-full " + (check.status === "success" ? "bg-accent" : "bg-amber-300")} />
                            <div className="min-w-[130px] flex-1">
                              <div className="text-xs font-medium text-slate-200">{check.indicator_key ?? check.series_id}</div>
                              <div className="mt-1 text-[10px] text-muted">
                                {check.series_id} · {new Date(check.checked_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                              </div>
                            </div>
                            <div className="text-right">
                              <div className={"text-[10px] uppercase tracking-[0.08em] " + (check.status === "success" ? "text-accent" : "text-amber-200")}>
                                {check.status === "success" ? "Success" : "Failed"}
                              </div>
                              <div className="mt-1 text-[10px] text-muted">
                                {check.elapsed_ms === null ? "—" : check.elapsed_ms + " ms"}
                                {check.latest_observation_date ? " · data " + check.latest_observation_date : ""}
                              </div>
                              {check.error_code ? <div className="mt-1 text-[10px] text-amber-200">{check.error_code}</div> : null}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="px-4 py-4 text-xs leading-5 text-muted">
                        No upstream fetch checks have been recorded yet. The first successful live source fetches will begin populating this list.
                      </p>
                    )}
                  </div>
                ) : null}
              </>
            ) : (
              <p className="text-sm text-muted">No archive status was returned.</p>
            )}
          </div>
        </section>


        <section
          aria-labelledby="revision-audit-title"
          className="mt-6 overflow-hidden rounded-2xl border border-line bg-panel/70"
        >
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-5 py-5 sm:px-7">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent">Data integrity / audit trail</div>
              <h2 id="revision-audit-title" className="mt-2 text-xl font-medium text-white">
                Source revision audit
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
                See when an upstream source changes a value for an observation date already stored in Arthvest. First-time imports are not revisions.
              </p>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-2 text-[10px] uppercase tracking-[0.12em] text-muted">
                Indicator
                <select
                  aria-label="Select indicator for revision audit"
                  value={revisionKey}
                  onChange={(event) => setRevisionKey(event.target.value)}
                  className="min-w-[220px] rounded-lg border border-line bg-[#0B1017] px-3 py-2.5 text-xs normal-case tracking-normal text-slate-100 outline-none transition focus:border-accent/60 focus:ring-2 focus:ring-accent/20"
                >
                  {comparisonOptions.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={() => setRevisionRetry((value) => value + 1)}
                className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2.5 text-xs text-slate-200 transition hover:border-accent/50 hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent/50"
              >
                <RefreshCw size={13} /> Refresh
              </button>
            </div>
          </div>
          <div className="p-5 sm:p-7">
            {revisionLoading ? (
              <div role="status" className="flex items-center gap-3 py-5 text-sm text-muted">
                <RefreshCw size={16} className="animate-spin" /> Loading revision audit…
              </div>
            ) : revisionError ? (
              <div role="status" className="rounded-xl border border-amber-300/20 bg-amber-300/[0.03] p-4">
                <div className="text-sm font-medium text-amber-100">Revision history unavailable</div>
                <p className="mt-2 text-xs leading-5 text-muted">{revisionError}</p>
                <p className="mt-2 text-xs leading-5 text-muted">
                  Revision history requires a reachable DATABASE_URL and at least two fetches of a stored observation when its upstream value changes.
                </p>
              </div>
            ) : revisionData && revisionData.revisions.length > 0 ? (
              <>
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm font-medium text-white">{revisionData.series_id} · detected revisions</div>
                  <div className="text-[10px] text-muted">Showing {revisionData.revisions.length} most recent records</div>
                </div>
                <div className="overflow-x-auto rounded-xl border border-line">
                  <table className="w-full min-w-[760px] border-collapse text-left">
                    <thead className="bg-[#0B1017] text-[10px] uppercase tracking-[0.1em] text-muted">
                      <tr>
                        <th className="px-4 py-3 font-medium">Observation date</th>
                        <th className="px-4 py-3 font-medium">Previous value</th>
                        <th className="px-4 py-3 font-medium">Revised value</th>
                        <th className="px-4 py-3 font-medium">Difference</th>
                        <th className="px-4 py-3 font-medium">Detected at</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {revisionData.revisions.map((revision, index) => {
                        const delta = revision.revised_value - revision.previous_value;
                        return (
                          <tr key={revision.series_id + "-" + revision.observation_date + "-" + revision.detected_at + "-" + index} className="text-xs text-slate-300">
                            <td className="px-4 py-3">{revision.observation_date}</td>
                            <td className="px-4 py-3 tabular-nums">{revision.previous_value.toLocaleString("en-US", { maximumFractionDigits: 5 })}</td>
                            <td className="px-4 py-3 tabular-nums">{revision.revised_value.toLocaleString("en-US", { maximumFractionDigits: 5 })}</td>
                            <td className={"px-4 py-3 tabular-nums " + (delta === 0 ? "text-muted" : "text-amber-200")}>
                              {delta > 0 ? "+" : ""}{delta.toLocaleString("en-US", { maximumFractionDigits: 5 })}
                            </td>
                            <td className="px-4 py-3 text-muted">
                              {new Date(revision.detected_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="mt-3 text-[10px] leading-5 text-muted">
                  Values are source-native. A detected revision records the difference between the previously retained value and the value observed during a later fetch.
                </p>
              </>
            ) : (
              <div className="rounded-xl border border-line bg-[#0B1017] p-5">
                <div className="text-sm font-medium text-white">No revisions detected for this series</div>
                <p className="mt-2 text-xs leading-5 text-muted">
                  That means no changed value has been recorded in the retained fetch history for this indicator. A newly created archive may have no revision history yet.
                </p>
              </div>
            )}
          </div>
        </section>

        <section
          aria-labelledby="historical-analytics-title"
          className="mt-6 overflow-hidden rounded-2xl border border-line bg-panel/70"
        >
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-5 py-5 sm:px-7">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent">Research tools / archived data</div>
              <h2 id="historical-analytics-title" className="mt-2 text-xl font-medium text-white">
                Historical trend analysis
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
                Compare the observation window&apos;s first and latest values, plus its range and dispersion. This is descriptive history, not a forecast or a calibrated macro regime score.
              </p>
            </div>
            <label className="flex flex-col gap-2 text-[10px] uppercase tracking-[0.12em] text-muted">
              Indicator
              <select
                aria-label="Select indicator for historical analytics"
                value={analyticsKey}
                onChange={(event) => setAnalyticsKey(event.target.value)}
                className="min-w-[220px] rounded-lg border border-line bg-[#0B1017] px-3 py-2.5 text-xs normal-case tracking-normal text-slate-100 outline-none transition focus:border-accent/60 focus:ring-2 focus:ring-accent/20"
              >
                <option value="fed-funds">Federal Funds Rate</option>
                <option value="us-inflation">U.S. CPI inflation YoY</option>
                <option value="us-unemployment">U.S. unemployment</option>
                <option value="india-gdp-growth">India real GDP growth</option>
                <option value="india-cpi-inflation-annual">India annual CPI inflation</option>
                <option value="india-policy-uncertainty">India policy uncertainty</option>
                <option value="usd-inr">INR per USD</option>
                <option value="india-reer">India REER</option>
              </select>
            </label>
          </div>

          <div className="p-5 sm:p-7">
            {analyticsLoading ? (
              <div role="status" className="flex items-center gap-3 py-5 text-sm text-muted">
                <RefreshCw size={16} className="animate-spin" /> Loading archived observations…
              </div>
            ) : analyticsError ? (
              <div role="status" className="flex flex-col items-start gap-3 rounded-xl border border-amber-300/20 bg-amber-300/[0.03] p-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3">
                  <Database size={18} className="mt-0.5 shrink-0 text-amber-200" />
                  <div>
                    <div className="text-sm font-medium text-amber-100">Archived analytics unavailable</div>
                    <p className="mt-2 max-w-3xl text-xs leading-5 text-muted">{analyticsError}</p>
                    <p className="mt-2 max-w-3xl text-xs leading-5 text-muted">
                      Configure a reachable DATABASE_URL on the backend and let successful source fetches populate the archive. Live indicator cards remain available separately.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setAnalyticsRetry((value) => value + 1)}
                  className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-slate-200 transition hover:border-accent/50 hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent/50"
                >
                  <RefreshCw size={13} /> Retry archive
                </button>
              </div>
            ) : historicalAnalytics ? (
              <>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="text-base font-medium text-white">{historicalAnalytics.indicator}</h3>
                    <p className="mt-1 text-xs leading-5 text-muted">
                      {historicalAnalytics.returned_count} observations
                      {historicalAnalytics.period_start && historicalAnalytics.period_end
                        ? " · " + formatObservationPeriod(historicalAnalytics.period_start, historicalAnalytics.frequency) + " – " + formatObservationPeriod(historicalAnalytics.period_end, historicalAnalytics.frequency)
                        : " · No archived window yet"}
                    </p>
                  </div>
                  <a
                    href={historicalAnalytics.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs text-slate-300 underline decoration-line underline-offset-4 transition hover:text-accent"
                  >
                    {historicalAnalytics.series_id} <ArrowUpRight size={12} />
                  </a>
                </div>

                {historicalAnalytics.returned_count < 2 ? (
                  <div role="status" className="mt-4 rounded-xl border border-amber-300/20 bg-amber-300/[0.03] p-4">
                    <div className="text-sm font-medium text-amber-100">Not enough archived history yet</div>
                    <p className="mt-1 text-xs leading-5 text-muted">
                      At least two display observations are needed for a directional comparison. The first successful source fetch can populate historical source observations.
                    </p>
                  </div>
                ) : null}

                <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-xl border border-line bg-[#0B1017] p-4">
                    <div className="text-[10px] text-muted">Latest value</div>
                    <div className="mt-2 text-2xl font-light text-white">
                      {historicalAnalytics.summary.latest_value === null ? "—" : historicalAnalytics.summary.latest_value.toLocaleString("en-US", { maximumFractionDigits: 3 })}
                    </div>
                    <div className="mt-1 break-words text-[10px] leading-4 text-muted">{historicalAnalytics.unit}</div>
                  </div>
                  <div className="rounded-xl border border-line bg-[#0B1017] p-4">
                    <div className="text-[10px] text-muted">Absolute change</div>
                    <div className="mt-2 text-2xl font-light text-white">
                      {historicalAnalytics.summary.absolute_change === null
                        ? "—"
                        : (historicalAnalytics.summary.absolute_change > 0 ? "+" : "") + historicalAnalytics.summary.absolute_change.toFixed(3)}
                    </div>
                    <div className="mt-1 text-[10px] leading-4 text-muted">{historicalAnalytics.change_unit}</div>
                  </div>
                  <div className="rounded-xl border border-line bg-[#0B1017] p-4">
                    <div className="text-[10px] text-muted">Direction across window</div>
                    <div className="mt-2 flex items-center gap-2 text-base font-medium text-white">
                      {historicalAnalytics.summary.direction === "higher" ? (
                        <TrendingUp size={17} className="text-amber-200" />
                      ) : historicalAnalytics.summary.direction === "lower" ? (
                        <TrendingDown size={17} className="text-accent" />
                      ) : (
                        <Minus size={17} className="text-muted" />
                      )}
                      {historicalAnalytics.summary.direction.replace("-", " ")}
                    </div>
                    <div className="mt-1 text-[10px] leading-4 text-muted">Descriptive, not a good/bad rating</div>
                  </div>
                  <div className="rounded-xl border border-line bg-[#0B1017] p-4">
                    <div className="text-[10px] text-muted">Relative change</div>
                    <div className="mt-2 text-2xl font-light text-white">
                      {historicalAnalytics.summary.relative_change_percent === null
                        ? "—"
                        : (historicalAnalytics.summary.relative_change_percent > 0 ? "+" : "") + historicalAnalytics.summary.relative_change_percent.toFixed(2) + "%"}
                    </div>
                    <div className="mt-1 text-[10px] leading-4 text-muted">Versus first returned value</div>
                  </div>
                </div>

                <div className="mt-4 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
                  <div className="rounded-xl border border-line bg-[#0B1017] p-4 sm:p-5">
                    <Sparkline points={historicalAnalytics.points} frequency={historicalAnalytics.frequency} />
                    <div className="mt-3 text-[10px] leading-5 text-muted">
                      {historicalAnalytics.calculation}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { label: "Window mean", value: historicalAnalytics.summary.mean },
                      { label: "Minimum", value: historicalAnalytics.summary.minimum },
                      { label: "Maximum", value: historicalAnalytics.summary.maximum },
                      { label: "Population σ", value: historicalAnalytics.summary.population_standard_deviation },
                    ].map((metric) => (
                      <div key={metric.label} className="rounded-xl border border-line bg-[#0B1017] p-3">
                        <div className="text-[10px] text-muted">{metric.label}</div>
                        <div className="mt-2 text-lg font-light text-white">
                          {metric.value === null ? "—" : metric.value.toLocaleString("en-US", { maximumFractionDigits: 3 })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <details className="mt-4 rounded-xl border border-line px-4 py-3">
                  <summary className="cursor-pointer text-xs font-medium text-slate-200">Methodology & limitations</summary>
                  <ul className="mt-3 list-disc space-y-1.5 pl-5 text-xs leading-5 text-muted">
                    {historicalAnalytics.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
                  </ul>
                  <p className="mt-3 text-[10px] text-muted">
                    Calculated {new Date(historicalAnalytics.generated_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                  </p>
                </details>
              </>
            ) : (
              <p className="text-sm text-muted">No historical analytics were returned.</p>
            )}
          </div>
        </section>


        <section
          aria-labelledby="macro-comparison-title"
          className="mt-6 overflow-hidden rounded-2xl border border-line bg-panel/70"
        >
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-5 py-5 sm:px-7">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent">Research tools / relative trends</div>
              <h2 id="macro-comparison-title" className="mt-2 text-xl font-medium text-white">
                Cross-indicator comparison
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
                Rebase each selected indicator to 100 at its first observation in the chosen calendar window. Compare relative movement, not raw units or economic desirability.
              </p>
            </div>
            <label className="flex flex-col gap-2 text-[10px] uppercase tracking-[0.12em] text-muted">
              Calendar window
              <select
                aria-label="Select comparison window"
                value={comparisonYears}
                onChange={(event) => setComparisonYears(Number(event.target.value))}
                className="min-w-[150px] rounded-lg border border-line bg-[#0B1017] px-3 py-2.5 text-xs normal-case tracking-normal text-slate-100 outline-none transition focus:border-accent/60 focus:ring-2 focus:ring-accent/20"
              >
                <option value={1}>1 year</option>
                <option value={3}>3 years</option>
                <option value={5}>5 years</option>
                <option value={10}>10 years</option>
              </select>
            </label>
          </div>

          <div className="p-5 sm:p-7">
            <div className="mb-5 flex flex-wrap gap-2.5" aria-label="Indicators to compare">
              {comparisonOptions.map((option) => {
                const checked = comparisonKeys.includes(option.key);
                const blocked =
                  (checked && comparisonKeys.length <= 2) ||
                  (!checked && comparisonKeys.length >= 5);
                return (
                  <label
                    key={option.key}
                    className={"inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs transition " +
                      (checked ? "border-accent/40 bg-accent/5 text-slate-100" : "border-line bg-[#0B1017] text-muted") +
                      (blocked ? " cursor-not-allowed opacity-60" : " cursor-pointer")}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={blocked}
                      onChange={(event) => {
                        setComparisonKeys((current) => {
                          if (event.target.checked) {
                            return current.length < 5 && !current.includes(option.key)
                              ? [...current, option.key]
                              : current;
                          }
                          return current.length > 2
                            ? current.filter((key) => key !== option.key)
                            : current;
                        });
                      }}
                      className="accent-sky-300"
                    />
                    {option.label}
                  </label>
                );
              })}
            </div>

            {comparisonLoading ? (
              <div role="status" className="flex items-center gap-3 py-5 text-sm text-muted">
                <RefreshCw size={16} className="animate-spin" /> Comparing archived observations…
              </div>
            ) : comparisonError ? (
              <div role="status" className="flex flex-col items-start gap-3 rounded-xl border border-amber-300/20 bg-amber-300/[0.03] p-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3">
                  <Database size={18} className="mt-0.5 shrink-0 text-amber-200" />
                  <div>
                    <div className="text-sm font-medium text-amber-100">Comparison unavailable</div>
                    <p className="mt-2 max-w-3xl text-xs leading-5 text-muted">{comparisonError}</p>
                    <p className="mt-2 max-w-3xl text-xs leading-5 text-muted">
                      This feature reads the persistent observation archive. Check that DATABASE_URL is configured and reachable, then allow the backend to archive source observations.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setComparisonRetry((value) => value + 1)}
                  className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-slate-200 transition hover:border-accent/50 hover:text-accent focus:outline-none focus:ring-2 focus:ring-accent/50"
                >
                  <RefreshCw size={13} /> Retry comparison
                </button>
              </div>
            ) : comparison ? (
              <>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-xs text-muted">
                    Requested window: {new Date(comparison.window_start + "T00:00:00").toLocaleDateString("en-IN", { month: "short", year: "numeric" })} – {new Date(comparison.window_end + "T00:00:00").toLocaleDateString("en-IN", { month: "short", year: "numeric" })}
                  </div>
                  <div className="text-[10px] text-muted">
                    {comparison.available_count} of {comparison.series.length} series normalizable
                  </div>
                </div>

                <ComparisonPlot comparison={comparison} />

                <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {comparison.series.map((series) => (
                    <article key={series.key} className="rounded-xl border border-line bg-[#0B1017] p-4">
                      <div className="flex items-start justify-between gap-3">
                        <h3 className="text-sm font-medium leading-5 text-white">{series.indicator}</h3>
                        <span className={"shrink-0 rounded-md border px-2 py-1 text-[9px] uppercase tracking-[0.08em] " +
                          (series.status === "available" ? "border-accent/25 bg-accent/5 text-accent" : "border-amber-300/25 bg-amber-300/5 text-amber-200")}>
                          {series.status === "available" ? "Indexed" : series.status.replace(/-/g, " ")}
                        </span>
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-3">
                        <div>
                          <div className="text-[10px] text-muted">Latest value</div>
                          <div className="mt-1 text-lg font-light text-white">
                            {series.latest_value === null ? "—" : series.latest_value.toLocaleString("en-US", { maximumFractionDigits: 3 })}
                          </div>
                          <div className="text-[9px] leading-4 text-muted">{series.unit}</div>
                        </div>
                        <div>
                          <div className="text-[10px] text-muted">Relative change</div>
                          <div className="mt-1 text-lg font-light text-white">
                            {series.relative_change_percent === null
                              ? "—"
                              : (series.relative_change_percent > 0 ? "+" : "") + series.relative_change_percent.toFixed(2) + "%"}
                          </div>
                          <div className="text-[9px] leading-4 text-muted">From first in-window value</div>
                        </div>
                      </div>
                      <div className="mt-3 border-t border-line pt-3 text-[10px] leading-5 text-muted">
                        <div>Baseline: {series.base_value === null ? "—" : series.base_value.toLocaleString("en-US", { maximumFractionDigits: 3 })} · {series.period_start ?? "no date"}</div>
                        <div>Latest observation: {series.period_end ?? "no date"} · {series.observation_count} points</div>
                        {series.reason ? <p className="mt-1 text-amber-200">{series.reason}</p> : null}
                      </div>
                      <a
                        href={series.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-3 inline-flex items-center gap-1.5 text-[10px] text-slate-300 underline decoration-line underline-offset-4 transition hover:text-accent"
                      >
                        Source · {series.series_id} <ArrowUpRight size={11} />
                      </a>
                    </article>
                  ))}
                </div>

                <details className="mt-4 rounded-xl border border-line px-4 py-3">
                  <summary className="cursor-pointer text-xs font-medium text-slate-200">Comparison methodology & limitations</summary>
                  <p className="mt-3 text-xs leading-5 text-muted">{comparison.methodology}</p>
                  <ul className="mt-3 list-disc space-y-1.5 pl-5 text-xs leading-5 text-muted">
                    {comparison.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
                  </ul>
                  <p className="mt-3 text-[10px] text-muted">
                    Calculated {new Date(comparison.generated_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                  </p>
                </details>
              </>
            ) : (
              <p className="text-sm text-muted">No macro comparison was returned.</p>
            )}
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
                              {component.observation_date ? `Observation ${formatObservationPeriod(component.observation_date, "Monthly")}` : "Observation unavailable"}
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
                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    {Object.entries(usScore.threshold_rules).map(([key, rules]) => (
                      <div key={key} className="rounded-lg border border-line bg-[#0B1017] p-3">
                        <div className="text-xs font-medium text-slate-200">
                          {usScore.components.find((component) => component.key === key)?.indicator ?? key}
                        </div>
                        <ul className="mt-2 space-y-1.5 text-[10px] leading-4 text-muted">
                          {rules.map((rule) => <li key={rule}>{rule}</li>)}
                        </ul>
                      </div>
                    ))}
                  </div>
                  <ul className="mt-4 list-disc space-y-1 pl-5 text-xs leading-5 text-muted">
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

        <section aria-labelledby="data-quality-title" className="mt-6 rounded-2xl border border-line bg-panel/60 p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent">Data integrity</div>
              <h2 id="data-quality-title" className="mt-2 text-lg font-medium text-white">Source coverage & freshness</h2>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-muted">
                Observation dates determine freshness. A successful retrieval alone does not mean a reading is current.
              </p>
            </div>
            {macroQuality ? (
              <span className={`rounded-full border px-3 py-1.5 text-[10px] uppercase tracking-[0.12em] ${
                macroQuality.quality_status === "good"
                  ? "border-accent/25 bg-accent/5 text-accent"
                  : "border-amber-300/25 bg-amber-300/5 text-amber-200"
              }`}>
                {macroQuality.quality_status}
              </span>
            ) : (
              <span className="rounded-full border border-line px-3 py-1.5 text-[10px] uppercase tracking-[0.12em] text-muted">
                {qualityError ? "quality unavailable" : "calculating"}
              </span>
            )}
          </div>

          {macroQuality ? (
            <>
              <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {[
                  { label: "Coverage", value: macroQuality.coverage_percent.toFixed(0) + "%" },
                  { label: "Fresh", value: String(macroQuality.fresh_count) },
                  { label: "In progress", value: String(macroQuality.in_progress_count) },
                  { label: "Stale", value: String(macroQuality.stale_count) },
                  { label: "Unavailable", value: String(macroQuality.unavailable_count) },
                ].map((metric) => (
                  <div key={metric.label} className="rounded-xl border border-line bg-[#0B1017] p-3">
                    <div className="text-[10px] text-muted">{metric.label}</div>
                    <div className="mt-2 text-xl font-light text-white">{metric.value}</div>
                  </div>
                ))}
              </div>
              <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-line">
                <div
                  className={`h-full rounded-full ${macroQuality.quality_status === "good" ? "bg-accent" : "bg-amber-300"}`}
                  style={{ width: macroQuality.coverage_percent + "%" }}
                />
              </div>
              <p className="mt-3 text-xs leading-5 text-muted">{macroQuality.note}</p>

              <div className="mt-5 overflow-x-auto rounded-xl border border-line">
                <div className="border-b border-line px-4 py-3">
                  <div className="text-xs font-medium text-slate-200">Per-indicator quality matrix</div>
                  <p className="mt-1 text-[10px] leading-5 text-muted">
                    Live source freshness is independent of the time the API was checked. Archived fetch details appear only when persistent storage is reachable.
                  </p>
                </div>
                <table className="w-full min-w-[920px] border-collapse text-left text-xs">
                  <thead className="bg-[#0B1017] text-[10px] uppercase tracking-[0.1em] text-muted">
                    <tr>
                      <th className="px-4 py-3 font-medium">Indicator</th>
                      <th className="px-4 py-3 font-medium">Quality</th>
                      <th className="px-4 py-3 font-medium">Observation</th>
                      <th className="px-4 py-3 font-medium">API retrieved</th>
                      <th className="px-4 py-3 font-medium">Latest archive check</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {macroQuality.indicators.map((qualityItem) => {
                      const overviewItem = macroOverview?.indicators.find((item) => item.key === qualityItem.key);
                      const data = overviewItem?.data ?? null;
                      const persistedCheck = sourceChecks?.checks.find((check) =>
                        check.indicator_key === qualityItem.key ||
                        (data !== null && check.series_id === data.series_id)
                      );
                      const freshness = qualityItem.status === "unavailable"
                        ? "unavailable"
                        : qualityItem.freshness_status ?? "unknown";
                      const statusClass = freshness === "fresh"
                        ? "border-accent/25 bg-accent/5 text-accent"
                        : "border-amber-300/25 bg-amber-300/5 text-amber-200";
                      let archiveLabel = "Not recorded";
                      let archiveDetail = "";
                      if (persistedCheck) {
                        archiveLabel = persistedCheck.status === "success" ? "Fetch succeeded" : "Fetch failed";
                        archiveDetail = new Date(persistedCheck.checked_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
                      } else if (!storageStatus?.enabled) {
                        archiveLabel = "Storage not configured";
                      } else if (!storageStatus.available) {
                        archiveLabel = "Storage unreachable";
                      }

                      return (
                        <tr key={qualityItem.key} className="align-top text-slate-300">
                          <td className="px-4 py-3">
                            <div className="font-medium text-slate-100">{data?.indicator ?? qualityItem.key}</div>
                            <div className="mt-1 text-[10px] text-muted">{data?.series_id ?? qualityItem.key}</div>
                          </td>
                          <td className="px-4 py-3">
                            <span className={"inline-flex rounded-md border px-2 py-1 text-[9px] uppercase tracking-[0.08em] " + statusClass}>
                              {freshness}
                            </span>
                            {qualityItem.issue ? <div className="mt-2 max-w-[190px] text-[10px] leading-4 text-muted">{qualityItem.issue}</div> : null}
                          </td>
                          <td className="px-4 py-3">
                            {data ? (
                              <>
                                <div>{formatObservationPeriod(data.observation_date, data.frequency)}</div>
                                <div className="mt-1 text-[10px] text-muted">{qualityItem.observation_age_days ?? data.observation_age_days} days old</div>
                              </>
                            ) : (
                              <span className="text-amber-200">No validated reading</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-muted">
                            {data
                              ? new Date(data.retrieved_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })
                              : "—"}
                          </td>
                          <td className="px-4 py-3">
                            <div className={persistedCheck?.status === "failure" ? "text-amber-200" : "text-slate-300"}>{archiveLabel}</div>
                            {archiveDetail ? <div className="mt-1 text-[10px] text-muted">{archiveDetail}</div> : null}
                            {persistedCheck?.error_code ? <div className="mt-1 text-[10px] text-amber-200">{persistedCheck.error_code}</div> : null}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p role="status" className="mt-4 text-xs text-muted">
              {qualityError ?? "Calculating quality from validated observations…"}
            </p>
          )}
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
                Source-attributed U.S. and Indian macroeconomic series plus foreign-exchange indicators. Period labels follow each source&apos;s publishing frequency; these are observations, not streaming market quotes.
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
                            {formatObservationPeriod(item.data.observation_date, item.data.frequency)}
                          </div>
                          <div className="mt-1 text-[10px] text-muted">
                            {item.data.observation_age_days} days after represented period end
                          </div>
                        </div>
                        {item.data.calculation ? (
                          <p className="mt-3 text-[11px] leading-5 text-muted">{item.data.calculation}</p>
                        ) : null}
                        <MacroDelta history={historyByKey[item.key]} unit={item.data.unit} />
                        {historyByKey[item.key] ? (
                          <Sparkline points={historyByKey[item.key]!.points} frequency={historyByKey[item.key]!.frequency} />
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
                            {item.data.series_id} · {item.data.frequency} · Retrieved {new Date(item.data.retrieved_at).toLocaleString("en-IN", {
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

        <details className="mt-4 overflow-hidden rounded-2xl border border-line bg-panel/50">
          <summary className="cursor-pointer px-5 py-4 text-sm font-medium text-slate-200 transition hover:text-accent sm:px-6">
            Indicator definitions, sources & freshness thresholds
            <span className="ml-2 text-xs font-normal text-muted">
              {macroCatalog ? `${macroCatalog.total_count} indicators` : catalogError ? "catalog unavailable" : "loading catalog"}
            </span>
          </summary>
          <div className="border-t border-line">
            {macroCatalog ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] border-collapse text-left text-xs">
                  <thead className="bg-[#0B1017] text-[10px] uppercase tracking-[0.12em] text-muted">
                    <tr>
                      <th className="px-4 py-3 font-medium">Indicator</th>
                      <th className="px-4 py-3 font-medium">Series / frequency</th>
                      <th className="px-4 py-3 font-medium">Freshness rule</th>
                      <th className="px-4 py-3 font-medium">Source & method</th>
                    </tr>
                  </thead>
                  <tbody>
                    {macroCatalog.indicators.map((indicator) => (
                      <tr key={indicator.key} className="border-t border-line/70 align-top">
                        <td className="px-4 py-4">
                          <div className="font-medium text-slate-200">{indicator.indicator}</div>
                          <div className="mt-1 max-w-xs leading-5 text-muted">{indicator.description}</div>
                        </td>
                        <td className="px-4 py-4 text-slate-300">
                          <div>{indicator.series_id}</div>
                          <div className="mt-1 text-muted">{indicator.frequency}</div>
                          <div className="mt-1 text-muted">{indicator.unit}</div>
                        </td>
                        <td className="px-4 py-4 text-slate-300">
                          {indicator.freshness_threshold_days} calendar days
                          <div className="mt-1 max-w-[150px] leading-5 text-muted">Provisional staleness threshold</div>
                        </td>
                        <td className="px-4 py-4">
                          <a href={indicator.source_url} target="_blank" rel="noreferrer" className="text-slate-200 underline decoration-line underline-offset-4 hover:text-accent">
                            {indicator.source}
                          </a>
                          <div className="mt-2 max-w-sm leading-5 text-muted">{indicator.calculation}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="px-5 py-4 text-xs text-muted">{catalogError ?? "Loading source definitions…"}</p>
            )}
          </div>
        </details>

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
