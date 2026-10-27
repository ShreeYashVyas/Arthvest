"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowLeft,
  ArrowUpRight,
  Clock3,
  ExternalLink,
  RefreshCw,
  ShieldCheck,
  TrendingUp,
  Wifi,
  WifiOff,
} from "lucide-react";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

type UpstoxStatus = {
  provider: string;
  configured: boolean;
  auth_mode: string | null;
  note: string;
};

type MarketQuote = {
  key: string;
  name: string;
  instrument_key: string;
  status: "available" | "unavailable";
  last_price: number | null;
  previous_close: number | null;
  change: number | null;
  change_percent: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  timestamp: string | null;
};

type MarketSnapshot = {
  provider: string;
  source_url: string;
  generated_at: string;
  data_as_of: string | null;
  available_count: number;
  total_count: number;
  quotes: MarketQuote[];
  read_only: boolean;
  limitations: string[];
};

const emptyQuotes: MarketQuote[] = [
  { key: "nifty-50", name: "NIFTY 50", instrument_key: "NSE_INDEX|Nifty 50", status: "unavailable", last_price: null, previous_close: null, change: null, change_percent: null, open: null, high: null, low: null, volume: null, timestamp: null },
  { key: "nifty-bank", name: "NIFTY BANK", instrument_key: "NSE_INDEX|Nifty Bank", status: "unavailable", last_price: null, previous_close: null, change: null, change_percent: null, open: null, high: null, low: null, volume: null, timestamp: null },
  { key: "india-vix", name: "INDIA VIX", instrument_key: "NSE_INDEX|India VIX", status: "unavailable", last_price: null, previous_close: null, change: null, change_percent: null, open: null, high: null, low: null, volume: null, timestamp: null },
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseStatus(value: unknown): UpstoxStatus {
  if (
    !isRecord(value) ||
    value.provider !== "Upstox" ||
    typeof value.configured !== "boolean" ||
    !(value.auth_mode === null || typeof value.auth_mode === "string") ||
    typeof value.note !== "string"
  ) {
    throw new Error("Upstox status returned an unexpected response format.");
  }
  return value as UpstoxStatus;
}

function parseSnapshot(value: unknown): MarketSnapshot {
  if (
    !isRecord(value) ||
    value.provider !== "Upstox" ||
    typeof value.source_url !== "string" ||
    typeof value.generated_at !== "string" ||
    !(value.data_as_of === null || typeof value.data_as_of === "string") ||
    typeof value.available_count !== "number" ||
    typeof value.total_count !== "number" ||
    !Array.isArray(value.quotes) ||
    value.read_only !== true ||
    !Array.isArray(value.limitations)
  ) {
    throw new Error("Market quote API returned an unexpected response format.");
  }
  return value as MarketSnapshot;
}

async function readJson(response: Response): Promise<unknown> {
  return response.json().catch(() => null);
}

function messageFrom(payload: unknown, fallback: string): string {
  if (isRecord(payload) && typeof payload.detail === "string") return payload.detail;
  return fallback;
}

function formatPrice(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatSigned(value: number | null, suffix = ""): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return sign + formatPrice(value) + suffix;
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Not supplied by provider";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function MarketsPage() {
  const [status, setStatus] = useState<UpstoxStatus | null>(null);
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMarketData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const statusResponse = await fetch(API_BASE_URL + "/api/market/upstox/status", {
        cache: "no-store",
      });
      const statusPayload = await readJson(statusResponse);
      if (!statusResponse.ok) {
        throw new Error(messageFrom(statusPayload, "Unable to check Upstox configuration."));
      }
      const nextStatus = parseStatus(statusPayload);
      setStatus(nextStatus);

      if (!nextStatus.configured) {
        setSnapshot(null);
        return;
      }

      const quotesResponse = await fetch(API_BASE_URL + "/api/market/upstox/quotes", {
        cache: "no-store",
      });
      const quotesPayload = await readJson(quotesResponse);
      if (!quotesResponse.ok) {
        throw new Error(messageFrom(quotesPayload, "Unable to retrieve market quotes."));
      }
      setSnapshot(parseSnapshot(quotesPayload));
    } catch (caught: unknown) {
      setSnapshot(null);
      setError(caught instanceof Error ? caught.message : "Market data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMarketData();
  }, [loadMarketData]);

  const quotes = snapshot?.quotes ?? emptyQuotes;
  const hasLiveQuotes = Boolean(snapshot && snapshot.available_count > 0);

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
              <div className="mt-0.5 text-[10px] uppercase tracking-[0.24em] text-muted">Market intelligence</div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
            <Link href="/" className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 transition hover:border-accent/50 hover:text-accent">
              <ArrowLeft size={13} /> Macro terminal
            </Link>
            <Link href="/agents" className="rounded-lg border border-line px-3 py-2 transition hover:border-accent/50 hover:text-accent">AI RESEARCH ↗</Link>
            <span className="hidden sm:inline">PHASE 02 / MARKET PULSE</span>
            <span className="h-4 w-px bg-line" />
            <span className="flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-2">
              {hasLiveQuotes ? <Wifi size={13} className="text-accent" /> : <WifiOff size={13} className="text-amber-300" />}
              <span className={hasLiveQuotes ? "text-accent" : "text-amber-300"}>
                {loading ? "CHECKING" : hasLiveQuotes ? "DATA CONNECTED" : status?.configured ? "TOKEN READY" : "TOKEN REQUIRED"}
              </span>
            </span>
          </div>
        </header>

        <section className="grid gap-8 py-9 lg:grid-cols-[1.3fr_0.7fr] lg:items-end lg:py-12">
          <div>
            <div className="mb-4 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.2em] text-accent">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              India · Market data snapshot
            </div>
            <h1 className="max-w-3xl text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl lg:text-6xl">
              See the <span className="text-accent">market pulse.</span>
              <br />Keep the signal honest.
            </h1>
            <p className="mt-5 max-w-2xl text-sm leading-7 text-muted sm:text-base">
              A read-only market snapshot for NIFTY 50, NIFTY BANK and India VIX, designed to sit beside Arthvest&apos;s macro indicators. Every displayed value comes from the provider response; unavailable data stays unavailable.
            </p>
          </div>

          <div className="rounded-2xl border border-line bg-panel/80 p-5 sm:p-6">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-muted">
                <Clock3 size={14} /> Provider status
              </div>
              <span className="rounded-md border border-line px-2 py-1 text-[10px] text-muted">READ ONLY</span>
            </div>
            <div className="mt-5">
              <div className="text-xl font-semibold text-white">
                {loading ? "Checking connection…" : status?.configured ? "Analytics token configured" : "Configuration needed"}
              </div>
              <p className="mt-2 text-xs leading-5 text-muted">
                {status?.note ?? "Checking the local Arthvest API."}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadMarketData()}
              disabled={loading}
              className="mt-5 inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-slate-200 transition hover:border-accent/50 hover:text-accent disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-accent/50"
            >
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh market data
            </button>
          </div>
        </section>

        {error ? (
          <div role="alert" className="mb-5 rounded-xl border border-amber-300/25 bg-amber-300/[0.04] p-4 text-sm leading-6 text-amber-100">
            {error}
          </div>
        ) : null}

        <section aria-labelledby="market-quotes-title">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-muted">Upstox · Market quote API</div>
              <h2 id="market-quotes-title" className="mt-2 text-xl font-medium text-white sm:text-2xl">Index snapshot</h2>
            </div>
            <div className="text-xs text-muted">
              {snapshot
                ? "Fetched " + formatTimestamp(snapshot.generated_at) + " · " + snapshot.available_count + "/" + snapshot.total_count + " available"
                : "No quote values are shown until the provider responds"}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {quotes.map((quote) => {
              const positive = quote.change !== null && quote.change >= 0;
              const hasQuote = quote.status === "available" && quote.last_price !== null;
              return (
                <article key={quote.key} className="rounded-2xl border border-line bg-panel/70 p-5 sm:p-6">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-xs font-medium tracking-[0.12em] text-muted">{quote.instrument_key}</div>
                      <h3 className="mt-2 text-lg font-medium text-white">{quote.name}</h3>
                    </div>
                    <span className={"rounded-full border px-2.5 py-1 text-[9px] uppercase tracking-[0.12em] " +
                      (hasQuote ? "border-accent/25 bg-accent/5 text-accent" : "border-line text-muted")}>
                      {hasQuote ? "Quote available" : loading ? "Loading" : "No data"}
                    </span>
                  </div>
                  <div className="mt-7">
                    <div className="text-3xl font-light tracking-tight text-white">
                      {hasQuote ? formatPrice(quote.last_price) : "—"}
                    </div>
                    <div className={"mt-2 flex items-center gap-1.5 text-sm " +
                      (!hasQuote || quote.change === null ? "text-muted" : positive ? "text-accent" : "text-rose-300")}>
                      {!hasQuote || quote.change === null ? null : positive ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}
                      {hasQuote ? formatSigned(quote.change) + " (" + formatSigned(quote.change_percent, "%") + ")" : "Waiting for a validated provider quote"}
                    </div>
                  </div>
                  <div className="mt-6 grid grid-cols-3 gap-2 border-t border-line pt-4">
                    {[
                      { label: "Open", value: quote.open },
                      { label: "High", value: quote.high },
                      { label: "Low", value: quote.low },
                    ].map((metric) => (
                      <div key={metric.label}>
                        <div className="text-[10px] text-muted">{metric.label}</div>
                        <div className="mt-1 text-sm text-slate-200">{hasQuote ? formatPrice(metric.value) : "—"}</div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 flex items-center gap-2 text-[10px] leading-4 text-muted">
                    <Clock3 size={12} />
                    Quote timestamp: {hasQuote ? formatTimestamp(quote.timestamp) : "Not available"}
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        {!status?.configured ? (
          <section aria-labelledby="setup-title" className="mt-6 overflow-hidden rounded-2xl border border-line bg-panel/70">
            <div className="border-b border-line px-5 py-5 sm:px-7">
              <div className="text-[10px] uppercase tracking-[0.2em] text-accent">One-time local setup</div>
              <h2 id="setup-title" className="mt-2 text-xl font-medium text-white">Connect your Upstox Analytics Token</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
                The page is ready, but the backend needs your token before it can request actual quotes. Never put the token in frontend code or send it through chat.
              </p>
            </div>
            <div className="grid gap-4 p-5 sm:grid-cols-3 sm:p-7">
              <div className="rounded-xl border border-line bg-[#0B1017] p-4">
                <div className="text-xs font-medium text-white">01 · Generate token</div>
                <p className="mt-2 text-xs leading-5 text-muted">Create an Analytics Token in the Upstox Developer Apps portal. It is read-only for market-data GET APIs.</p>
                <a href="https://account.upstox.com/developer/apps" target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-2 text-xs text-accent hover:underline">
                  Developer Apps <ExternalLink size={12} />
                </a>
              </div>
              <div className="rounded-xl border border-line bg-[#0B1017] p-4">
                <div className="text-xs font-medium text-white">02 · Save it privately</div>
                <p className="mt-2 text-xs leading-5 text-muted">Open backend/.env and set the variable below. Keep the value local and out of GitHub.</p>
                <code className="mt-3 block break-all rounded-lg border border-line bg-panel px-3 py-2 text-[11px] text-slate-200">UPSTOX_ANALYTICS_TOKEN=your_token_here</code>
              </div>
              <div className="rounded-xl border border-line bg-[#0B1017] p-4">
                <div className="text-xs font-medium text-white">03 · Restart the API</div>
                <p className="mt-2 text-xs leading-5 text-muted">From the backend folder, run the command below so Uvicorn reads your local .env file.</p>
                <code className="mt-3 block break-all rounded-lg border border-line bg-panel px-3 py-2 text-[11px] text-slate-200">uvicorn app.main:app --reload --env-file .env</code>
              </div>
            </div>
          </section>
        ) : null}

        {snapshot ? (
          <section aria-labelledby="provenance-title" className="mt-6 overflow-hidden rounded-2xl border border-line bg-panel/70">
            <div className="border-b border-line px-5 py-5 sm:px-7">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-accent">
                <ShieldCheck size={14} /> Data provenance and limits
              </div>
              <h2 id="provenance-title" className="mt-2 text-xl font-medium text-white">Know what this feed does — and does not — mean</h2>
            </div>
            <div className="grid gap-4 p-5 sm:grid-cols-2 sm:p-7">
              <div className="rounded-xl border border-line bg-[#0B1017] p-4">
                <div className="flex items-center gap-2 text-sm font-medium text-white"><TrendingUp size={15} /> Quote provenance</div>
                <p className="mt-2 text-xs leading-5 text-muted">
                  Provider: {snapshot.provider}. Snapshot fetched at {formatTimestamp(snapshot.generated_at)}. Latest provider timestamp: {formatTimestamp(snapshot.data_as_of)}.
                </p>
                <a href={snapshot.source_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-2 text-xs text-accent hover:underline">
                  Upstox quote API documentation <ExternalLink size={12} />
                </a>
              </div>
              <div className="rounded-xl border border-line bg-[#0B1017] p-4">
                <div className="flex items-center gap-2 text-sm font-medium text-white"><ShieldCheck size={15} /> Read-only by design</div>
                <ul className="mt-2 space-y-2 text-xs leading-5 text-muted">
                  {snapshot.limitations.map((limitation) => <li key={limitation}>• {limitation}</li>)}
                </ul>
              </div>
            </div>
          </section>
        ) : null}

        <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5 text-[10px] leading-5 text-muted">
          <span>ARTHVEST · MACRO + MARKET INTELLIGENCE</span>
          <span className="flex items-center gap-2"><ShieldCheck size={12} /> No order placement · No credential exposure · No fabricated quotes</span>
        </footer>
      </div>
    </main>
  );
}
