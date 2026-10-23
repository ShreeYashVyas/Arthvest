"use client";

import { useEffect, useState } from "react";
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

export default function Home() {
  const [serviceState, setServiceState] = useState<ServiceState>("checking");
  const [checkedAt, setCheckedAt] = useState<string>("—");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    const baseUrl = (
      process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
    ).replace(/\/$/, "");

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
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">The scoring model is not active yet. Readings will appear after source adapters, validation rules and scoring methodology are implemented.</p>
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
