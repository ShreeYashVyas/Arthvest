"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
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
import {
  fetchMarketProviderStatus,
  fetchMarketQuotes,
  type MarketProviderStatus,
  type MarketQuote,
  type MarketQuotesResponse,
} from "@/lib/api";
import StockDiscovery from "./StockDiscovery";

const INSTRUMENTS = [
  { key: "nifty-50", name: "NIFTY 50", instrumentId: "NSE_INDEX|Nifty 50" },
  { key: "nifty-bank", name: "NIFTY BANK", instrumentId: "NSE_INDEX|Nifty Bank" },
  { key: "india-vix", name: "INDIA VIX", instrumentId: "NSE_INDEX|India VIX" },
] as const;

const configuredRefreshSeconds = Number(process.env.NEXT_PUBLIC_MARKET_REFRESH_SECONDS);
const refreshSeconds = Number.isFinite(configuredRefreshSeconds) && configuredRefreshSeconds > 0
  ? Math.min(300, Math.max(30, Math.trunc(configuredRefreshSeconds)))
  : 60;

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "Not supplied by provider";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Timestamp unavailable";
  return parsed.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function formatAge(value: string): string {
  const parsed = new Date(value).getTime();
  if (!Number.isFinite(parsed)) return "age unknown";
  const seconds = Math.max(0, Math.floor((Date.now() - parsed) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m ago`;
}

function formatPrice(value: number | null, currency: string | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const options: Intl.NumberFormatOptions = {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  };
  if (currency) {
    options.style = "currency";
    options.currency = currency;
    options.currencyDisplay = "narrowSymbol";
  }
  return new Intl.NumberFormat("en-IN", options).format(value);
}

function formatSigned(value: number | null, currency: string | null, suffix = ""): string {
  if (value === null || !Number.isFinite(value)) return "Not supplied";
  const sign = value > 0 ? "+" : "";
  return sign + formatPrice(value, currency) + suffix;
}

function freshnessLabel(quote: MarketQuote): string {
  if (quote.status === "unavailable") return "Unavailable";
  switch (quote.freshness) {
    case "fresh": return "Fresh provider timestamp";
    case "delayed": return "Delayed · not real-time";
    case "stale": return "Stale provider timestamp";
    default: return "Provider timestamp unknown";
  }
}

function quoteClass(quote: MarketQuote): string {
  if (quote.status === "unavailable" || quote.freshness === "stale") return "text-amber-200";
  if (quote.freshness === "fresh") return "text-accent";
  return "text-muted";
}

export default function MarketsPage() {
  const [providerStatus, setProviderStatus] = useState<MarketProviderStatus | null>(null);
  const [snapshot, setSnapshot] = useState<MarketQuotesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const requestInFlight = useRef<Promise<void> | null>(null);

  const refreshMarketData = useCallback((): Promise<void> => {
    if (requestInFlight.current) return requestInFlight.current;

    setRefreshing(true);
    const request = (async () => {
      try {
        const status = await fetchMarketProviderStatus();
        setProviderStatus(status);
        const quotes = await fetchMarketQuotes(INSTRUMENTS.map((item) => item.key));
        setSnapshot(quotes);
        setError(null);
      } catch (caught: unknown) {
        setError(caught instanceof Error ? caught.message : "Market data could not be refreshed.");
      } finally {
        setInitialLoading(false);
        setRefreshing(false);
      }
    })();
    requestInFlight.current = request;
    void request.then(() => {
      if (requestInFlight.current === request) requestInFlight.current = null;
    });
    return request;
  }, []);

  useEffect(() => {
    void refreshMarketData();
    const timer = window.setInterval(() => void refreshMarketData(), refreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [refreshMarketData]);

  const quotesByKey = new Map((snapshot?.quotes ?? []).map((quote) => [quote.key, quote]));
  const hasAnyQuote = (snapshot?.available_count ?? 0) > 0;
  const snapshotAvailable = hasAnyQuote;

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
            <span className="hidden sm:inline">PHASE 02 / MARKET PULSE</span>
            <span className="h-4 w-px bg-line" />
            <span className="flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-2">
              {snapshotAvailable ? <Wifi size={13} className="text-accent" /> : <WifiOff size={13} className="text-amber-300" />}
              <span className={snapshotAvailable ? "text-accent" : "text-amber-300"}>
                {initialLoading ? "FETCHING SNAPSHOT" : snapshotAvailable ? "SNAPSHOT AVAILABLE" : "DATA UNAVAILABLE"}
              </span>
            </span>
          </div>
        </header>

        <section className="grid gap-8 py-9 lg:grid-cols-[1.3fr_0.7fr] lg:items-end lg:py-12">
          <div>
            <div className="mb-4 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.2em] text-accent">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" /> India · Market data snapshot
            </div>
            <h1 className="max-w-3xl text-4xl font-semibold leading-[1.08] tracking-tight text-white sm:text-5xl lg:text-6xl">
              See the <span className="text-accent">market pulse.</span>
              <br />Keep the signal honest.
            </h1>
            <p className="mt-5 max-w-2xl text-sm leading-7 text-muted sm:text-base">
              NIFTY 50, NIFTY BANK and India VIX snapshots come from the selected backend provider. If a quote or its timestamp is missing, it remains missing.
            </p>
          </div>

          <div className="rounded-2xl border border-line bg-panel/80 p-5 sm:p-6">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-muted">
                <Clock3 size={14} /> Market data provider
              </div>
              <span className="rounded-md border border-line px-2 py-1 text-[10px] text-muted">READ ONLY</span>
            </div>
            <div className="mt-5">
              <div className="text-xl font-semibold text-white">
                {initialLoading ? "Connecting…" : providerStatus?.provider ?? "Provider unavailable"}
              </div>
              <p className="mt-2 text-xs leading-5 text-muted">
                {providerStatus?.note ?? "Checking the Arthvest market-data API."}
              </p>
              <p className="mt-2 text-[11px] text-muted">
                V3 feed: {!providerStatus ? "checking" : providerStatus.provider !== "Upstox" ? "not selected" : providerStatus.stream_configured ? providerStatus.connection_state : "credentials unavailable"}
                {providerStatus?.stream_configured ? ` · ${providerStatus.subscribed_instrument_count} instruments · last tick ${formatTimestamp(providerStatus.last_tick_received_at)}` : " · REST snapshots remain available"}
              </p>
              <p className="mt-2 text-[11px] text-muted">Automatic refresh every {refreshSeconds} seconds.</p>
            </div>
            <button
              type="button"
              onClick={() => void refreshMarketData()}
              disabled={refreshing}
              className="mt-5 inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-slate-200 transition hover:border-accent/50 hover:text-accent disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-accent/50"
            >
              <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
              {refreshing ? "Refreshing…" : "Refresh market data"}
            </button>
          </div>
        </section>

        <StockDiscovery streamConfigured={providerStatus?.stream_configured ?? null} />

        {error ? (
          <div role="alert" className="mb-5 rounded-xl border border-amber-300/25 bg-amber-300/[0.04] p-4 text-sm leading-6 text-amber-100">
            <div>{error}</div>
            {snapshot ? (
              <div className="mt-1 text-xs text-amber-100/75">
                Showing the last successful response from {formatAge(snapshot.fetched_at)}; its original source timestamp and freshness labels are unchanged.
              </div>
            ) : null}
          </div>
        ) : null}

        <section aria-labelledby="market-quotes-title">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-muted">
                {snapshot?.provider ?? providerStatus?.provider ?? "Selected provider"} · Quotes
              </div>
              <h2 id="market-quotes-title" className="mt-2 text-xl font-medium text-white sm:text-2xl">Index snapshot</h2>
            </div>
            <div className="text-xs text-muted">
              {snapshot
                ? `Fetched ${formatTimestamp(snapshot.fetched_at)} · ${snapshot.available_count}/${snapshot.total_count} available${snapshot.cached ? " · cached" : ""}`
                : "No quote values have been returned by the backend yet"}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {INSTRUMENTS.map((instrument) => {
              const quote = quotesByKey.get(instrument.key);
              const available = quote?.status === "available" && quote.last_price !== null;
              const positive = quote?.change !== null && quote?.change !== undefined && quote.change >= 0;
              return (
                <article key={instrument.key} className="rounded-2xl border border-line bg-panel/70 p-5 sm:p-6">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-xs font-medium tracking-[0.12em] text-muted">{quote?.instrument_id ?? instrument.instrumentId}</div>
                      <h3 className="mt-2 text-lg font-medium text-white">{quote?.symbol ?? instrument.name}</h3>
                    </div>
                    <span className={`rounded-full border px-2.5 py-1 text-[9px] uppercase tracking-[0.12em] ${quote ? quoteClass(quote) : "border-line text-muted"}`}>
                      {quote ? freshnessLabel(quote) : initialLoading ? "Loading" : "No quote"}
                    </span>
                  </div>
                  <div className="mt-7">
                    <div className="text-3xl font-light tracking-tight text-white">
                      {available && quote ? formatPrice(quote.last_price, quote.currency) : "—"}
                    </div>
                    <div className={`mt-2 flex items-center gap-1.5 text-sm ${!available || !quote?.change ? "text-muted" : positive ? "text-accent" : "text-rose-300"}`}>
                      {!available || quote?.change === null || quote?.change === undefined
                        ? null
                        : positive ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}
                      {available && quote
                        ? `${formatSigned(quote.change, quote.currency)} (${formatSigned(quote.change_percent, null, "%")})`
                        : "No provider quote available"}
                    </div>
                  </div>
                  <div className="mt-6 grid grid-cols-2 gap-2 border-t border-line pt-4 text-[10px] leading-4 text-muted">
                    <div>Source</div><div className="text-right text-slate-200">{quote?.source ?? "Not available"}</div>
                    <div>Source timestamp</div><div className="text-right text-slate-200">{formatTimestamp(quote?.source_timestamp)}</div>
                    <div>Fetched</div><div className="text-right text-slate-200">{quote ? formatAge(quote.fetched_at) : "Not fetched"}</div>
                    <div>Currency</div><div className="text-right text-slate-200">{quote?.currency ?? "Not supplied"}</div>
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <section aria-labelledby="history-title" className="mt-6 rounded-2xl border border-line bg-panel/70 p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-accent">
            <TrendingUp size={14} /> Historical data
          </div>
          <h2 id="history-title" className="mt-2 text-lg font-medium text-white">No historical chart is available</h2>
          <p className="mt-2 text-xs leading-5 text-muted">
            The configured provider currently supplies quote snapshots only. Arthvest will show a chart when a historical-data endpoint is available; no sample series are displayed.
          </p>
        </section>

        {providerStatus?.provider === "Upstox" ? (
          <section className="mt-6 rounded-2xl border border-line bg-panel/70 p-5 sm:p-6">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-accent">
              <ShieldCheck size={14} /> Provider provenance
            </div>
            <p className="mt-2 text-xs leading-5 text-muted">
              Upstox quotes use a backend-only read-only Analytics Token. The credential is never sent to this page or included in API responses.
            </p>
            <a href="https://upstox.com/developer/api-documentation/get-full-market-quote/" target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-2 text-xs text-accent hover:underline">
              Upstox quote API documentation <ExternalLink size={12} />
            </a>
          </section>
        ) : providerStatus?.provider === "Yahoo Finance" ? (
          <section className="mt-6 rounded-2xl border border-line bg-panel/70 p-5 sm:p-6">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-accent">
              <ShieldCheck size={14} /> Provider provenance
            </div>
            <p className="mt-2 text-xs leading-5 text-muted">
              Yahoo Finance chart data is best-effort and may be delayed or stale. Check each quote&apos;s source timestamp; Arthvest does not label this feed real-time.
            </p>
            {snapshot ? (
              <a href={snapshot.source_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-2 text-xs text-accent hover:underline">
                Yahoo Finance source <ExternalLink size={12} />
              </a>
            ) : null}
          </section>
        ) : null}

        <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5 text-[10px] leading-5 text-muted">
          <span>ARTHVEST · MACRO + MARKET INTELLIGENCE</span>
          <span className="flex items-center gap-2"><ShieldCheck size={12} /> Read-only data · No credential exposure · No sample prices</span>
        </footer>
      </div>
    </main>
  );
}
