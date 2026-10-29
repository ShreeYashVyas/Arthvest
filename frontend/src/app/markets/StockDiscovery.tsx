"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Check, ChevronLeft, ChevronRight, Clock3, Plus, RefreshCw, Search, Star, Trash2, Wifi, WifiOff, X } from "lucide-react";
import {
  createWatchlist,
  deleteWatchlist,
  fetchInstrumentHistory,
  fetchInstrumentQuote,
  fetchWatchlists,
  marketStreamUrl,
  renameWatchlist,
  replaceWatchlistEntries,
  searchMarketInstruments,
  type InstrumentSearchResponse,
  type MarketCandle,
  type MarketInstrument,
  type MarketInstrumentQuote,
  type MarketWatchlist,
} from "@/lib/api";

const MAX_WATCHLIST_SIZE = 20;

function formatTime(value: string | null | undefined): string {
  if (!value) return "Not supplied";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Timestamp unavailable" : parsed.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function formatAge(value: string | null): string {
  if (!value) return "No upstream message received";
  const ageSeconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (!Number.isFinite(ageSeconds)) return "Message age unavailable";
  if (ageSeconds < 60) return `${ageSeconds}s ago`;
  if (ageSeconds < 3600) return `${Math.floor(ageSeconds / 60)}m ago`;
  return `${Math.floor(ageSeconds / 3600)}h ago`;
}

function money(value: number | null | undefined, currency = "INR"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
}

function freshness(quote: MarketInstrumentQuote | undefined): string {
  if (!quote || quote.status !== "available") return "Unavailable";
  if (quote.freshness === "stale") return "Stale source data";
  if (!quote.source_timestamp) return "Timestamp unknown";
  const sourceTime = new Date(quote.source_timestamp).getTime();
  if (!Number.isFinite(sourceTime)) return "Timestamp unknown";
  const ageSeconds = (Date.now() - sourceTime) / 1000;
  if (ageSeconds < -2) return "Timestamp unknown";
  if (ageSeconds > 300) return "Stale source data";
  if (quote.freshness === "fresh") return "Fresh snapshot";
  return "Timestamp unknown";
}

function quoteTint(quote: MarketInstrumentQuote | undefined): string {
  if (!quote || quote.status !== "available" || freshness(quote) === "Stale source data") return "text-amber-200";
  return freshness(quote) === "Fresh snapshot" ? "text-accent" : "text-muted";
}

function PriceChart({ candles }: { candles: MarketCandle[] }) {
  const points = useMemo(() => {
    if (!candles.length) return "";
    const values = candles.map((candle) => candle.close);
    const low = Math.min(...values);
    const high = Math.max(...values);
    const spread = high - low || Math.max(Math.abs(high) * 0.01, 1);
    return values.map((value, index) => {
      const x = candles.length === 1 ? 450 : (index / (candles.length - 1)) * 900;
      const y = 210 - ((value - low) / spread) * 190;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
  }, [candles]);
  if (!candles.length) {
    return <div className="grid min-h-52 place-items-center rounded-xl border border-dashed border-line text-sm text-muted">No historical candles were returned for this range.</div>;
  }
  return (
    <div className="rounded-xl border border-line bg-[#0B1017] p-3">
      <svg className="h-56 w-full overflow-visible" viewBox="0 0 900 230" preserveAspectRatio="none" role="img" aria-label={`Historical daily closing prices from ${candles[0].timestamp} to ${candles[candles.length - 1].timestamp}`}>
        <path d={points} fill="none" stroke="currentColor" strokeWidth="2.5" vectorEffect="non-scaling-stroke" className="text-accent" />
      </svg>
      <div className="flex justify-between text-[10px] text-muted"><span>{formatTime(candles[0].timestamp)}</span><span>{formatTime(candles[candles.length - 1].timestamp)}</span></div>
    </div>
  );
}

export default function StockDiscovery({ streamConfigured }: { streamConfigured: boolean | null }) {
  const [query, setQuery] = useState("");
  const [exchange, setExchange] = useState<"ALL" | "NSE" | "BSE">("ALL");
  const [page, setPage] = useState(1);
  const [searchRevision, setSearchRevision] = useState(0);
  const [searchResponse, setSearchResponse] = useState<InstrumentSearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const [selected, setSelected] = useState<MarketInstrument | null>(null);
  const selectedInstrumentKeyRef = useRef<string | null>(null);
  const quoteRequestRevision = useRef(0);
  const manualQuoteControllerRef = useRef<AbortController | null>(null);
  selectedInstrumentKeyRef.current = selected?.instrument_key ?? null;
  const [selectedQuote, setSelectedQuote] = useState<MarketInstrumentQuote | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteError, setQuoteError] = useState<string | null>(null);
  const [candles, setCandles] = useState<MarketCandle[]>([]);
  const [historyFetchedAt, setHistoryFetchedAt] = useState<string | null>(null);
  const [technicalIndicators, setTechnicalIndicators] = useState<Awaited<ReturnType<typeof fetchInstrumentHistory>>["technical_indicators"] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyRange, setHistoryRange] = useState<"1M" | "3M" | "1Y" | "5Y">("1Y");
  const [streamState, setStreamState] = useState("disconnected");
  const [lastStreamMessageAt, setLastStreamMessageAt] = useState<string | null>(null);
  const [, setAgeRefresh] = useState(0);
  const [watchlists, setWatchlists] = useState<MarketWatchlist[]>([]);
  const [activeWatchlistId, setActiveWatchlistId] = useState<number | null>(null);
  const [watchlistName, setWatchlistName] = useState("");
  const [watchlistRename, setWatchlistRename] = useState("");
  const [watchlistQuotes, setWatchlistQuotes] = useState<Record<string, MarketInstrumentQuote>>({});
  const [watchlistReady, setWatchlistReady] = useState(false);
  const [watchlistSaving, setWatchlistSaving] = useState(false);
  const [watchlistError, setWatchlistError] = useState<string | null>(null);
  const [watchlistQuoteError, setWatchlistQuoteError] = useState<string | null>(null);
  const watchlist = useMemo(
    () => watchlists.find((item) => item.id === activeWatchlistId)?.instruments ?? [],
    [watchlists, activeWatchlistId],
  );

  useEffect(() => {
    if (!selected) return;
    const timer = window.setInterval(() => setAgeRefresh((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [selected]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSearchResponse(null);
      setSearchError(null);
      setSearching(false);
      return () => controller.abort();
    }
    setSearching(true);
    const timer = window.setTimeout(() => {
      void searchMarketInstruments(trimmed, exchange, page, controller.signal)
        .then((response) => { if (active) { setSearchResponse(response); setSearchError(null); setActiveIndex(-1); } })
        .catch((error: unknown) => {
          if (active && !(error instanceof DOMException && error.name === "AbortError")) {
            setSearchError(error instanceof Error ? error.message : "Instrument search failed.");
            setSearchResponse(null);
          }
        })
        .finally(() => { if (active) setSearching(false); });
    }, 300);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [query, exchange, page, searchRevision]);

  useEffect(() => {
    const controller = new AbortController();
    void fetchWatchlists(controller.signal)
      .then((items) => {
        if (controller.signal.aborted) return;
        setWatchlists(items);
        setActiveWatchlistId(items[0]?.id ?? null);
        setWatchlistRename(items[0]?.name ?? "");
        setWatchlistError(null);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setWatchlistError(error instanceof Error ? error.message : "Saved watchlists are unavailable.");
      })
      .finally(() => { if (!controller.signal.aborted) setWatchlistReady(true); });
    return () => controller.abort();
  }, []);

  const refreshWatchlist = useCallback(async (signal: AbortSignal) => {
    const outcomes = await Promise.allSettled(watchlist.map((instrument) => fetchInstrumentQuote(instrument.instrument_key, signal)));
    if (signal.aborted) return;
    const updated: Record<string, MarketInstrumentQuote> = {};
    outcomes.forEach((outcome, index) => {
      if (outcome.status === "fulfilled") updated[watchlist[index].instrument_key] = outcome.value.quote;
    });
    setWatchlistQuotes((current) => ({ ...current, ...updated }));
    setWatchlistQuoteError(outcomes.some((outcome) => outcome.status === "rejected") ? "Some watchlist quotes could not be refreshed." : null);
  }, [watchlist]);

  useEffect(() => {
    if (!watchlistReady || !watchlist.length) return;
    const controller = new AbortController();
    void refreshWatchlist(controller.signal);
    const timer = window.setInterval(() => void refreshWatchlist(controller.signal), 60_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [watchlistReady, refreshWatchlist, watchlist.length]);

  useEffect(() => {
    if (!selected) return;
    const key = selected.instrument_key;
    const controller = new AbortController();
    const requestRevision = ++quoteRequestRevision.current;
    setQuoteLoading(true);
    setQuoteError(null);
    void fetchInstrumentQuote(key, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted && quoteRequestRevision.current === requestRevision) {
          setSelectedQuote(response.quote);
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && quoteRequestRevision.current === requestRevision) {
          setQuoteError(error instanceof Error ? error.message : "Quote unavailable.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted && quoteRequestRevision.current === requestRevision) setQuoteLoading(false);
      });
    return () => {
      controller.abort();
      manualQuoteControllerRef.current?.abort();
      manualQuoteControllerRef.current = null;
      if (quoteRequestRevision.current === requestRevision) quoteRequestRevision.current += 1;
    };
  }, [selected]);

  useEffect(() => {
    if (!selected) return;
    const key = selected.instrument_key;
    let stopped = false;
    let attempts = 0;
    let retryAllowed = true;
    let retryTimer: number | undefined;
    let socket: WebSocket | null = null;
    const connect = () => {
      if (stopped) return;
      setStreamState(attempts ? "reconnecting" : "connecting");
      socket = new WebSocket(marketStreamUrl(key));
      socket.onmessage = (event) => {
        if (selectedInstrumentKeyRef.current !== key) return;
        try {
          const message: unknown = JSON.parse(String(event.data));
          if (typeof message !== "object" || message === null) return;
          const data = message as { type?: unknown; state?: unknown; detail?: unknown; received_at?: unknown; message_received_at?: unknown; quote?: MarketInstrumentQuote };
          if (data.type === "connected") setStreamState("connected");
          else if (data.type === "connection" && typeof data.state === "string") {
            setStreamState(data.state);
            if (typeof data.message_received_at === "string") setLastStreamMessageAt(data.message_received_at);
          } else if (data.type === "quote" && data.quote?.instrument_key === key && selectedInstrumentKeyRef.current === key) {
            setSelectedQuote((previous) => ({ ...(previous ?? {} as MarketInstrumentQuote), ...data.quote }));
            setLastStreamMessageAt(typeof data.received_at === "string" ? data.received_at : data.quote.fetched_at);
            setStreamState("streaming");
          } else if (data.type === "unavailable") {
            retryAllowed = false;
            setQuoteError(typeof data.detail === "string" ? data.detail : "Live feed unavailable.");
            setStreamState(typeof data.state === "string" ? data.state : "unavailable");
          } else if (data.type === "disconnected") setStreamState("disconnected");
        } catch { setStreamState("unavailable"); }
      };
      socket.onerror = () => setStreamState("disconnected");
      socket.onclose = () => {
        if (stopped) return;
        if (!retryAllowed) {
          setStreamState("unavailable");
          return;
        }
        if (attempts < 3) {
          const delay = Math.min(4000, 500 * (2 ** attempts));
          attempts += 1;
          retryTimer = window.setTimeout(connect, delay);
          setStreamState("reconnecting");
        } else setStreamState("disconnected");
      };
    };
    if (streamConfigured === false) setStreamState("unavailable");
    else if (streamConfigured === true) connect();
    return () => {
      stopped = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      if (socket?.readyState === WebSocket.OPEN) socket.send("unsubscribe");
      socket?.close();
    };
  }, [selected, streamConfigured]);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setCandles([]);
    setHistoryFetchedAt(null);
    setTechnicalIndicators(null);
    setHistoryLoading(true);
    setHistoryError(null);
    void fetchInstrumentHistory(selected.instrument_key, controller.signal, historyRange)
      .then((response) => {
        if (!controller.signal.aborted) {
          setCandles(response.candles);
          setHistoryFetchedAt(response.fetched_at);
          setTechnicalIndicators(response.technical_indicators ?? null);
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setHistoryError(error instanceof Error ? error.message : "Historical data unavailable.");
      })
      .finally(() => { if (!controller.signal.aborted) setHistoryLoading(false); });
    return () => controller.abort();
  }, [selected, historyRange]);

  useEffect(() => {
    if (!selected || !["disconnected", "unavailable"].includes(streamState)) return;
    const key = selected.instrument_key;
    const refresh = () => void fetchInstrumentQuote(key).then((result) => setSelectedQuote(result.quote)).catch((error: unknown) => setQuoteError(error instanceof Error ? error.message : "REST quote fallback failed."));
    const timer = window.setInterval(refresh, 60_000);
    return () => window.clearInterval(timer);
  }, [selected, streamState]);

  const results = searchResponse?.instruments ?? [];
  const watchlistKeys = new Set(watchlist.map((item) => item.instrument_key));
  const quoteStats = [
    ["Previous close", money(selectedQuote?.previous_close)],
    ["Open", money(selectedQuote?.open)],
    ["High / Low", `${money(selectedQuote?.high)} / ${money(selectedQuote?.low)}`],
    ["Volume", selectedQuote?.volume === null || selectedQuote?.volume === undefined ? "—" : new Intl.NumberFormat("en-IN").format(selectedQuote.volume)],
  ];

  const chooseInstrument = (instrument: MarketInstrument) => {
    setSelected(instrument);
    setSelectedQuote(null);
    setLastStreamMessageAt(null);
    setCandles([]);
    setStreamState("connecting");
    setPage(1);
  };

  const toggleWatchlist = async (instrument: MarketInstrument) => {
    if (activeWatchlistId === null) {
      setWatchlistError("Create or select a server watchlist before adding instruments.");
      return;
    }
    const next = watchlistKeys.has(instrument.instrument_key)
      ? watchlist.filter((item) => item.instrument_key !== instrument.instrument_key)
      : [...watchlist, instrument];
    if (next.length > MAX_WATCHLIST_SIZE) {
      setWatchlistError(`A watchlist is limited to ${MAX_WATCHLIST_SIZE} instruments.`);
      return;
    }
    setWatchlistSaving(true);
    try {
      const updated = await replaceWatchlistEntries(activeWatchlistId, next.map((item) => item.instrument_key));
      setWatchlists((items) => items.map((item) => item.id === updated.id ? updated : item));
      setWatchlistError(null);
    } catch (error) {
      setWatchlistError(error instanceof Error ? error.message : "Watchlist change was not saved.");
    } finally {
      setWatchlistSaving(false);
    }
  };

  const createNewWatchlist = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!watchlistName.trim()) return;
    setWatchlistSaving(true);
    try {
      const created = await createWatchlist(watchlistName.trim());
      setWatchlists((items) => [...items, created]);
      setActiveWatchlistId(created.id);
      setWatchlistRename(created.name);
      setWatchlistName("");
      setWatchlistError(null);
    } catch (error) {
      setWatchlistError(error instanceof Error ? error.message : "Watchlist could not be created.");
    } finally {
      setWatchlistSaving(false);
    }
  };

  const saveWatchlistName = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (activeWatchlistId === null || !watchlistRename.trim()) return;
    setWatchlistSaving(true);
    try {
      const updated = await renameWatchlist(activeWatchlistId, watchlistRename.trim());
      setWatchlists((items) => items.map((item) => item.id === updated.id ? updated : item));
      setWatchlistError(null);
    } catch (error) {
      setWatchlistError(error instanceof Error ? error.message : "Watchlist name was not saved.");
    } finally {
      setWatchlistSaving(false);
    }
  };

  const removeWatchlist = async () => {
    if (activeWatchlistId === null) return;
    setWatchlistSaving(true);
    try {
      await deleteWatchlist(activeWatchlistId);
      const remaining = watchlists.filter((item) => item.id !== activeWatchlistId);
      setWatchlists(remaining);
      setActiveWatchlistId(remaining[0]?.id ?? null);
      setWatchlistRename(remaining[0]?.name ?? "");
      setWatchlistError(null);
    } catch (error) {
      setWatchlistError(error instanceof Error ? error.message : "Watchlist could not be deleted.");
    } finally {
      setWatchlistSaving(false);
    }
  };

  const manualQuoteRefresh = async () => {
    if (!selected) return;
    const instrumentKey = selected.instrument_key;
    const requestRevision = ++quoteRequestRevision.current;
    manualQuoteControllerRef.current?.abort();
    const controller = new AbortController();
    manualQuoteControllerRef.current = controller;
    setQuoteLoading(true);
    try {
      const response = await fetchInstrumentQuote(instrumentKey, controller.signal);
      if (quoteRequestRevision.current !== requestRevision || selectedInstrumentKeyRef.current !== instrumentKey) return;
      setSelectedQuote(response.quote);
      setQuoteError(null);
    } catch (error) {
      if (!controller.signal.aborted && quoteRequestRevision.current === requestRevision && selectedInstrumentKeyRef.current === instrumentKey) {
        setQuoteError(error instanceof Error ? error.message : "Quote refresh failed.");
      }
    } finally {
      if (manualQuoteControllerRef.current === controller) manualQuoteControllerRef.current = null;
      if (!controller.signal.aborted && quoteRequestRevision.current === requestRevision && selectedInstrumentKeyRef.current === instrumentKey) {
        setQuoteLoading(false);
      }
    }
  };

  const handleSearchKey = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" && results.length) {
      event.preventDefault(); setActiveIndex((index) => Math.min(results.length - 1, index + 1));
    } else if (event.key === "ArrowUp" && results.length) {
      event.preventDefault(); setActiveIndex((index) => Math.max(0, index - 1));
    } else if (event.key === "Enter" && activeIndex >= 0 && results[activeIndex]) {
      event.preventDefault(); chooseInstrument(results[activeIndex]);
    } else if (event.key === "Escape") {
      setQuery(""); setSearchResponse(null); setActiveIndex(-1);
    }
  };

  return (
    <section className="mt-8 space-y-6" aria-labelledby="stock-discovery-title">
      <div className="rounded-2xl border border-line bg-panel/70 p-5 sm:p-7">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-accent">Upstox supported instrument universe · NSE + BSE equities</div>
            <h2 id="stock-discovery-title" className="mt-2 text-xl font-medium text-white sm:text-2xl">Find a listed company</h2>
          </div>
          <span className="text-xs text-muted">Search provider: {searchResponse?.source ?? "Upstox instrument search"}</span>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_150px_auto]">
          <label className="relative block">
            <span className="sr-only">Search company, trading symbol, or ISIN</span>
            <Search size={17} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input
              ref={inputRef} value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }}
              onKeyDown={handleSearchKey} role="combobox" aria-expanded={results.length > 0}
              aria-controls="instrument-results" aria-autocomplete="list"
              aria-activedescendant={activeIndex >= 0 ? `instrument-option-${activeIndex}` : undefined}
              placeholder="Company name, symbol, or ISIN" autoComplete="off"
              className="w-full rounded-xl border border-line bg-[#0B1017] py-3 pl-10 pr-10 text-sm text-white outline-none placeholder:text-muted focus:border-accent/60 focus:ring-2 focus:ring-accent/20"
            />
            {query ? <button type="button" aria-label="Clear search" onClick={() => { setQuery(""); setSearchResponse(null); inputRef.current?.focus(); }} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-white"><X size={16} /></button> : null}
          </label>
          <label className="sr-only" htmlFor="stock-exchange">Exchange</label>
          <select id="stock-exchange" value={exchange} onChange={(event) => { setExchange(event.target.value as "ALL" | "NSE" | "BSE"); setPage(1); }} className="rounded-xl border border-line bg-[#0B1017] px-3 py-3 text-sm text-slate-200 outline-none focus:border-accent/60">
            <option value="ALL">All exchanges</option><option value="NSE">NSE</option><option value="BSE">BSE</option>
          </select>
          <button type="button" onClick={() => { setPage(1); setSearchRevision((value) => value + 1); }} disabled={searching || query.trim().length < 2} className="inline-flex items-center justify-center gap-2 rounded-xl border border-line px-4 py-3 text-sm text-white hover:border-accent/50 disabled:opacity-50"><RefreshCw size={15} className={searching ? "animate-spin" : ""} /> Search</button>
        </div>
        <div className="mt-2 flex justify-between text-[10px] text-muted"><span>Results contain instruments returned by Upstox; NSE/BSE listings remain separate.</span><span>{searching ? "Searching…" : searchResponse ? `${searchResponse.page.total_records} matches` : ""}</span></div>
        {searchError ? <div role="alert" className="mt-4 flex items-center gap-2 rounded-lg border border-rose-300/20 bg-rose-300/5 p-3 text-xs text-rose-200"><AlertCircle size={14} />{searchError}<button type="button" className="ml-auto underline" onClick={() => setSearchRevision((value) => value + 1)}>Retry</button></div> : null}
        {query.trim().length >= 2 && !searching && !searchError && searchResponse && results.length === 0 ? <div className="mt-4 rounded-lg border border-dashed border-line p-5 text-center text-sm text-muted">No supported equities matched this search.</div> : null}
        {results.length ? (
          <div id="instrument-results" role="listbox" aria-label="Matching NSE and BSE equity instruments" className="mt-4 divide-y divide-line overflow-hidden rounded-xl border border-line">
            {results.map((instrument, index) => (
              <div key={instrument.instrument_key} id={`instrument-option-${index}`} role="option" aria-selected={activeIndex === index} onMouseEnter={() => setActiveIndex(index)} className={`flex flex-wrap items-center gap-3 px-4 py-3 ${activeIndex === index ? "bg-accent/5" : "bg-[#0B1017]/70"}`}>
                <button type="button" onClick={() => chooseInstrument(instrument)} className="min-w-0 flex-1 text-left focus:outline-none focus:ring-2 focus:ring-accent/50">
                  <span className="block truncate text-sm font-medium text-white">{instrument.name}</span>
                  <span className="mt-1 block truncate text-[11px] text-muted">{instrument.trading_symbol} · {instrument.exchange} · {instrument.segment} · {instrument.instrument_type}{instrument.isin ? ` · ${instrument.isin}` : ""}</span>
                </button>
                <button type="button" disabled={!watchlistReady || watchlistSaving} onClick={() => void toggleWatchlist(instrument)} aria-label={watchlistKeys.has(instrument.instrument_key) ? "Remove from watchlist" : "Add to watchlist"} className="rounded-lg border border-line p-2 text-muted hover:text-accent disabled:opacity-40">{watchlistKeys.has(instrument.instrument_key) ? <Check size={15} /> : <Plus size={15} />}</button>
              </div>
            ))}
          </div>
        ) : null}
        {searchResponse && searchResponse.page.total_pages > 1 ? (
          <div className="mt-3 flex items-center justify-end gap-2 text-xs text-muted">
            <button type="button" disabled={page <= 1 || searching} onClick={() => setPage((value) => Math.max(1, value - 1))} className="rounded-lg border border-line p-2 disabled:opacity-40"><ChevronLeft size={15} /></button>
            <span>Page {page} of {searchResponse.page.total_pages}</span>
            <button type="button" disabled={page >= searchResponse.page.total_pages || searching} onClick={() => setPage((value) => value + 1)} className="rounded-lg border border-line p-2 disabled:opacity-40"><ChevronRight size={15} /></button>
          </div>
        ) : null}
      </div>

      <div className="rounded-2xl border border-line bg-panel/70 p-5 sm:p-7">
        <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="flex items-center gap-2 text-sm font-medium text-white"><Star size={15} className="text-accent" /> Server watchlists</h3><span className="text-[10px] text-muted">Single-user development scope · saved by Core API</span></div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          <form onSubmit={createNewWatchlist} className="flex gap-2">
            <label className="sr-only" htmlFor="new-watchlist-name">New watchlist name</label>
            <input id="new-watchlist-name" value={watchlistName} onChange={(event) => setWatchlistName(event.target.value)} maxLength={50} placeholder="New watchlist name" className="min-w-0 flex-1 rounded-lg border border-line bg-[#0B1017] px-3 py-2 text-xs text-white" />
            <button type="submit" disabled={watchlistSaving || !watchlistName.trim()} className="rounded-lg border border-line px-3 py-2 text-xs text-white disabled:opacity-40">Create</button>
          </form>
          <label className="flex items-center gap-2 text-xs text-muted">Active list
            <select aria-label="Active watchlist" value={activeWatchlistId ?? ""} onChange={(event) => {
              const id = Number(event.target.value);
              setActiveWatchlistId(Number.isFinite(id) && id > 0 ? id : null);
              setWatchlistRename(watchlists.find((item) => item.id === id)?.name ?? "");
            }} className="min-w-0 flex-1 rounded-lg border border-line bg-[#0B1017] px-3 py-2 text-xs text-white">
              <option value="">Choose a saved watchlist</option>
              {watchlists.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <div className="flex gap-2">
            <form onSubmit={saveWatchlistName} className="flex min-w-0 flex-1 gap-2">
              <label className="sr-only" htmlFor="rename-watchlist">Rename active watchlist</label>
              <input id="rename-watchlist" value={watchlistRename} onChange={(event) => setWatchlistRename(event.target.value)} maxLength={50} placeholder="Rename active list" disabled={activeWatchlistId === null} className="min-w-0 flex-1 rounded-lg border border-line bg-[#0B1017] px-3 py-2 text-xs text-white disabled:opacity-40" />
              <button type="submit" disabled={watchlistSaving || activeWatchlistId === null || !watchlistRename.trim()} className="rounded-lg border border-line px-3 py-2 text-xs text-white disabled:opacity-40">Rename</button>
            </form>
            <button type="button" onClick={() => void removeWatchlist()} disabled={watchlistSaving || activeWatchlistId === null} className="rounded-lg border border-line px-3 py-2 text-xs text-rose-200 disabled:opacity-40">Delete</button>
          </div>
        </div>
        {watchlistError ? <p role="status" className="mt-3 text-xs text-amber-200">{watchlistError}</p> : null}
        {watchlistQuoteError ? <p role="status" className="mt-2 text-xs text-amber-200">{watchlistQuoteError}</p> : null}
        {!watchlistReady ? <p role="status" className="mt-4 text-xs text-muted">Loading saved watchlists…</p> : null}
        {watchlistReady && !watchlistError && !watchlists.length ? <p className="mt-4 text-xs text-muted">Create a list to save instruments on the server.</p> : null}
        {watchlistReady && activeWatchlistId !== null && !watchlist.length ? <p className="mt-4 text-xs text-muted">This saved watchlist has no instruments yet.</p> : null}
        <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {watchlist.map((instrument) => {
            const quote = watchlistQuotes[instrument.instrument_key];
            return <div key={instrument.instrument_key} className="flex items-center gap-2 rounded-xl border border-line bg-[#0B1017]/70 p-3">
              <button type="button" onClick={() => chooseInstrument(instrument)} className="min-w-0 flex-1 text-left"><span className="block truncate text-xs font-medium text-white">{instrument.trading_symbol} · {instrument.exchange}</span><span className={`mt-1 block text-[10px] ${quoteTint(quote)}`}>{quote ? `${money(quote.last_price)} · ${freshness(quote)}` : "Quote unavailable"}</span><span className="mt-1 block truncate text-[9px] text-muted">{quote ? `${quote.source} · source ${formatTime(quote.source_timestamp)} · fetched ${formatTime(quote.fetched_at)}` : "No provider quote timestamp"}</span></button>
              <button type="button" disabled={watchlistSaving} aria-label={`Remove ${instrument.trading_symbol} from watchlist`} onClick={() => void toggleWatchlist(instrument)} className="rounded-lg p-2 text-muted hover:text-rose-200 disabled:opacity-40"><Trash2 size={14} /></button>
            </div>;
          })}
        </div>
      </div>

      {selected ? (
        <div className="space-y-4 rounded-2xl border border-line bg-panel/70 p-5 sm:p-7" aria-labelledby="selected-stock-title">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><div className="text-[10px] uppercase tracking-[0.2em] text-accent">{selected.exchange} · {selected.segment} · {selected.instrument_key}</div><h3 id="selected-stock-title" className="mt-2 text-2xl font-medium text-white">{selected.name}</h3><p className="mt-1 text-xs text-muted">{selected.trading_symbol}{selected.isin ? ` · ISIN ${selected.isin}` : ""} · Source Upstox</p></div>
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={!watchlistReady || watchlistSaving} onClick={() => void toggleWatchlist(selected)} className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-slate-200 hover:border-accent/50 disabled:opacity-40"><Star size={13} />{watchlistKeys.has(selected.instrument_key) ? "Remove watchlist" : "Add to watchlist"}</button>
              <button type="button" onClick={() => void manualQuoteRefresh()} disabled={quoteLoading} className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs text-slate-200 hover:border-accent/50 disabled:opacity-50"><RefreshCw size={13} className={quoteLoading ? "animate-spin" : ""} />Refresh quote</button>
              <button type="button" onClick={() => setSelected(null)} className="rounded-lg border border-line p-2 text-muted hover:text-white" aria-label="Close stock detail"><X size={15} /></button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-[11px]">
            <span className={`inline-flex items-center gap-1.5 ${streamState === "streaming" ? "text-accent" : "text-muted"}`}>{["streaming", "connected"].includes(streamState) ? <Wifi size={13} /> : <WifiOff size={13} />}{streamState === "streaming" ? "Streaming connection" : streamState === "connected" ? "Feed connected · awaiting provider tick" : streamState === "connecting" || streamState === "reconnecting" ? `Feed ${streamState}` : streamConfigured === false ? "Live feed credentials unavailable · REST snapshot fallback" : streamState === "unauthorized" ? "Feed unauthorized · REST snapshot fallback" : streamState === "disconnected" ? "Feed disconnected · REST snapshot fallback" : "Live feed unavailable · REST snapshot fallback"}</span>
            <span className="text-muted">Displayed quote: {selectedQuote?.delivery === "stream" ? "Streaming" : selectedQuote ? "REST snapshot" : "Unavailable"}</span>
            <span className="text-muted"><Clock3 size={12} className="mr-1 inline" />Last upstream message {formatAge(lastStreamMessageAt)}</span>
            <span className="text-muted"><Clock3 size={12} className="mr-1 inline" />Fetched {selectedQuote ? formatTime(selectedQuote.fetched_at) : "—"}</span>
            <span className={`rounded-full border border-line px-2 py-1 ${quoteTint(selectedQuote ?? undefined)}`}>{freshness(selectedQuote ?? undefined)}</span>
          </div>
          {quoteError ? <div role="alert" className="rounded-lg border border-amber-300/20 bg-amber-300/5 p-3 text-xs text-amber-100">{quoteError}</div> : null}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-line bg-[#0B1017] p-4"><div className="text-[10px] uppercase text-muted">Last traded price · {selectedQuote?.source ?? "Upstox"}</div><div className="mt-2 text-2xl text-white">{money(selectedQuote?.last_price)}</div><div className={`mt-1 text-xs ${selectedQuote?.change !== null && selectedQuote?.change !== undefined && selectedQuote.change < 0 ? "text-rose-200" : "text-accent"}`}>{selectedQuote?.change !== null && selectedQuote?.change !== undefined ? `${selectedQuote.change > 0 ? "+" : ""}${money(selectedQuote.change)} (${selectedQuote.change_percent === null ? "—" : `${selectedQuote.change_percent.toFixed(2)}%`})` : "Change unavailable"}</div></div>
            {quoteStats.map(([label, value]) => <div key={label} className="rounded-xl border border-line bg-[#0B1017] p-4"><div className="text-[10px] uppercase text-muted">{label}</div><div className="mt-2 text-xl text-white">{value}</div></div>)}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3"><div><h4 className="text-sm font-medium text-white">Historical daily closes</h4><p className="mt-1 text-[10px] text-muted">Upstox V3 candles · {historyRange} range · Retrieved {formatTime(historyFetchedAt)}{candles.length ? ` · Latest candle ${formatTime(candles[candles.length - 1].timestamp)}` : ""}</p></div><div className="flex items-center gap-3"><label htmlFor="stock-history-range" className="text-[10px] text-muted">Time range</label><select id="stock-history-range" value={historyRange} onChange={(event) => setHistoryRange(event.target.value as "1M" | "3M" | "1Y" | "5Y")} className="rounded-lg border border-line bg-[#0B1017] px-2 py-1.5 text-xs text-slate-200"><option value="1M">1 month</option><option value="3M">3 months</option><option value="1Y">1 year</option><option value="5Y">5 years</option></select><span className="text-[10px] text-muted">{historyLoading ? "Loading…" : `${candles.length} candles`}</span></div></div>
          {historyError ? <div role="status" className="rounded-lg border border-amber-300/20 bg-amber-300/5 p-3 text-xs text-amber-100">{historyError}</div> : null}
          <PriceChart candles={candles} />
          <div className="rounded-xl border border-line bg-[#0B1017] p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 className="text-xs font-medium text-slate-200">Technical indicators</h4>
              <span className="text-[10px] text-muted">{technicalIndicators?.input_candle_count ?? 0} verified candles · calculated on backend</span>
            </div>
            {technicalIndicators?.status === "available" ? (
              <div className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-3 xl:grid-cols-5">
                {[["SMA 10", "sma_10"], ["SMA 20", "sma_20"], ["SMA 50", "sma_50"], ["SMA 100", "sma_100"], ["SMA 200", "sma_200"], ["EMA 9", "ema_9"], ["EMA 12", "ema_12"], ["EMA 20", "ema_20"], ["EMA 26", "ema_26"], ["EMA 50", "ema_50"], ["RSI 14", "rsi_14"], ["MACD 12/26/9", "macd"], ["MACD signal", "macd_signal"], ["ATR 14", "atr_14"], ["Bollinger upper", "bollinger_upper_20_2"], ["Bollinger middle", "bollinger_middle_20"], ["Bollinger lower", "bollinger_lower_20_2"], ["Stochastic %K", "stochastic_k_14"], ["Stochastic %D", "stochastic_d_3"], ["ROC 12 (%)", "roc_12_percent"], ["Momentum 10", "momentum_10"], ["OBV", "obv"], ["ADX 14", "adx_14"], ["Session VWAP", "vwap_session"]].map(([label, key]) => {
                  const value = technicalIndicators.values[key] ?? null;
                  const unavailable = value === null ? key === "vwap_session" ? "Unavailable for daily candles" : "Insufficient history" : value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
                  return <div key={key}><div className="text-[10px] text-muted">{label}</div><div className="mt-1 font-medium text-slate-200">{unavailable}</div></div>;
                })}
              </div>
            ) : <p className="mt-3 text-xs text-muted">Indicators are unavailable until the selected range provides enough valid candles.</p>}
          </div>
          {selectedQuote?.source_timestamp ? <p className="text-[10px] text-muted">Quote source timestamp: {formatTime(selectedQuote.source_timestamp)} · Backend fetch: {formatTime(selectedQuote.fetched_at)}</p> : null}
        </div>
      ) : null}
    </section>
  );
}
