import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StockDiscovery from "./StockDiscovery";
import {
  createWatchlist,
  deleteWatchlist,
  fetchInstrumentHistory,
  fetchInstrumentQuote,
  fetchWatchlists,
  renameWatchlist,
  replaceWatchlistEntries,
  searchMarketInstruments,
  type InstrumentSearchResponse,
  type MarketInstrument,
  type MarketInstrumentQuoteResponse,
  type MarketWatchlist,
} from "@/lib/api";

vi.mock("@/lib/api", () => ({
  createWatchlist: vi.fn(),
  deleteWatchlist: vi.fn(),
  fetchInstrumentHistory: vi.fn(),
  fetchInstrumentQuote: vi.fn(),
  fetchWatchlists: vi.fn(),
  marketStreamUrl: vi.fn((key: string) => `ws://localhost/api/market/stream/${key}`),
  renameWatchlist: vi.fn(),
  replaceWatchlistEntries: vi.fn(),
  searchMarketInstruments: vi.fn(),
}));

const RELIANCE: MarketInstrument = {
  instrument_key: "NSE_EQ|INE002A01018",
  trading_symbol: "RELIANCE",
  name: "Reliance Industries Ltd",
  short_name: "Reliance Industries",
  exchange: "NSE",
  segment: "NSE_EQ",
  instrument_type: "EQ",
  isin: "INE002A01018",
  lot_size: 1,
  tick_size: 0.05,
  source: "Upstox instrument master",
  catalogue_updated_at: "2026-10-29T10:00:00+00:00",
};

const SEARCH_RESPONSE: InstrumentSearchResponse = {
  query: "Reliance",
  exchange: "ALL",
  instruments: [RELIANCE],
  page: { page_number: 1, total_pages: 1, records: 20, total_records: 1 },
  source: "Upstox instrument master",
  catalogue_updated_at: "2026-10-29T10:00:00+00:00",
};

const QUOTE_RESPONSE: MarketInstrumentQuoteResponse = {
  provider: "Upstox",
  source_url: "https://upstox.com/developer/api-documentation/get-full-market-quote/",
  fetched_at: "2026-10-29T10:00:02+00:00",
  cached: false,
  quote: {
    instrument_key: RELIANCE.instrument_key,
    symbol: RELIANCE.trading_symbol,
    name: RELIANCE.name,
    exchange: RELIANCE.exchange,
    segment: RELIANCE.segment,
    instrument_type: "EQ",
    isin: RELIANCE.isin,
    last_price: 1500,
    change: 10,
    change_percent: 0.67,
    previous_close: 1490,
    open: 1495,
    high: 1505,
    low: 1490,
    volume: 1000,
    currency: "INR",
    source: "Upstox",
    delivery: "rest",
    source_timestamp: "2026-10-29T10:00:00+00:00",
    fetched_at: "2026-10-29T10:00:02+00:00",
    freshness: "fresh",
    status: "available",
  },
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

class MockWebSocket {
  static OPEN = 1;
  static instances: MockWebSocket[] = [];
  url: string;
  readyState = MockWebSocket.OPEN;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  sent: string[] = [];
  closed = false;

  constructor(url: string) { this.url = url; MockWebSocket.instances.push(this); }
  send(message: string) { this.sent.push(message); }
  close() { this.closed = true; this.readyState = 3; }
}

const mockedSearch = vi.mocked(searchMarketInstruments);
const mockedQuote = vi.mocked(fetchInstrumentQuote);
const mockedHistory = vi.mocked(fetchInstrumentHistory);
const mockedWatchlists = vi.mocked(fetchWatchlists);
const mockedCreateWatchlist = vi.mocked(createWatchlist);
const mockedRenameWatchlist = vi.mocked(renameWatchlist);
const mockedDeleteWatchlist = vi.mocked(deleteWatchlist);
const mockedReplaceEntries = vi.mocked(replaceWatchlistEntries);

function makeWatchlist(instruments: MarketInstrument[] = [], name = "Core", id = 1): MarketWatchlist {
  return { id, name, instruments, created_at: "2026-10-29T10:00:00Z", updated_at: "2026-10-29T10:00:00Z" };
}

beforeEach(() => {
  vi.clearAllMocks();
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
  mockedSearch.mockResolvedValue(SEARCH_RESPONSE);
  mockedQuote.mockResolvedValue(QUOTE_RESPONSE);
  mockedWatchlists.mockResolvedValue([makeWatchlist()]);
  mockedCreateWatchlist.mockImplementation(async (name) => makeWatchlist([], name, 2));
  mockedRenameWatchlist.mockImplementation(async (id, name) => makeWatchlist([], name, id));
  mockedDeleteWatchlist.mockResolvedValue();
  mockedReplaceEntries.mockImplementation(async (id, keys) => makeWatchlist(
    keys.map((key) => ({ ...RELIANCE, instrument_key: key, exchange: key.startsWith("BSE_EQ") ? "BSE" : "NSE", segment: key.startsWith("BSE_EQ") ? "BSE_EQ" : "NSE_EQ" })),
    "Core", id,
  ));
  mockedHistory.mockResolvedValue({
    instrument_key: RELIANCE.instrument_key,
    symbol: RELIANCE.trading_symbol,
    exchange: "NSE",
    provider: "Upstox",
    unit: "days",
    interval: 1,
    from_date: "2026-09-29",
    to_date: "2026-10-29",
    fetched_at: "2026-10-29T10:00:02+00:00",
    candles: [],
  });
});

afterEach(() => vi.unstubAllGlobals());

describe("StockDiscovery", () => {
  it("debounces search input and displays provider instruments", async () => {
    render(<StockDiscovery streamConfigured={false} />);
    fireEvent.change(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { target: { value: "Reliance" } });

    expect(mockedSearch).not.toHaveBeenCalled();
    await screen.findByText("Reliance Industries Ltd");
    expect(mockedSearch).toHaveBeenCalledTimes(1);
    expect(mockedSearch).toHaveBeenCalledWith("Reliance", "ALL", 1, expect.any(AbortSignal));
    fireEvent.keyDown(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { key: "ArrowDown" });
    fireEvent.keyDown(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { key: "Enter" });
    expect(await screen.findByRole("heading", { name: "Reliance Industries Ltd" })).toBeTruthy();
  });

  it("does not let an older response replace results for a newer query", async () => {
    const oldResponse = deferred<InstrumentSearchResponse>();
    const newResponse = deferred<InstrumentSearchResponse>();
    mockedSearch.mockImplementation((query) => query === "Reliance" ? oldResponse.promise : newResponse.promise);
    render(<StockDiscovery streamConfigured={false} />);
    const input = screen.getByPlaceholderText("Company name, symbol, or ISIN");

    fireEvent.change(input, { target: { value: "Reliance" } });
    await waitFor(() => expect(mockedSearch).toHaveBeenCalledTimes(1));
    fireEvent.change(input, { target: { value: "TCS" } });
    await waitFor(() => expect(mockedSearch).toHaveBeenCalledTimes(2));

    const tcs = { ...RELIANCE, instrument_key: "NSE_EQ|INE467B01029", trading_symbol: "TCS", name: "Tata Consultancy Services" };
    await act(async () => newResponse.resolve({ ...SEARCH_RESPONSE, query: "TCS", instruments: [tcs] }));
    expect(await screen.findByText("Tata Consultancy Services")).toBeTruthy();
    await act(async () => oldResponse.resolve(SEARCH_RESPONSE));
    expect(screen.queryByText("Reliance Industries Ltd")).toBeNull();
  });

  it("persists watchlist identity through Core and fetches one initial REST quote without stream credentials", async () => {
    render(<StockDiscovery streamConfigured={false} />);
    fireEvent.change(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { target: { value: "Reliance" } });
    const result = await screen.findByText("Reliance Industries Ltd");
    fireEvent.click(result);
    await screen.findByText("Live feed credentials unavailable · REST snapshot fallback");
    await screen.findByText("₹1,500.00");
    expect(mockedQuote).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getAllByRole("button", { name: /Add to watchlist/i }).at(-1)!);
    await waitFor(() => expect(mockedReplaceEntries).toHaveBeenCalledWith(1, [RELIANCE.instrument_key]));
    expect(await screen.findByText("RELIANCE · NSE")).toBeTruthy();
  });

  it("keeps failed watchlist saves visibly unsaved", async () => {
    mockedReplaceEntries.mockRejectedValueOnce(new Error("Watchlist storage is temporarily unavailable."));
    render(<StockDiscovery streamConfigured={false} />);
    fireEvent.change(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { target: { value: "Reliance" } });
    fireEvent.click(await screen.findByText("Reliance Industries Ltd"));
    fireEvent.click(screen.getAllByRole("button", { name: /Add to watchlist/i }).at(-1)!);
    expect(await screen.findByText("Watchlist storage is temporarily unavailable.")).toBeTruthy();
    expect(screen.getByText("This saved watchlist has no instruments yet.")).toBeTruthy();
  });

  it("cleans up the WebSocket subscription when the selected detail closes", async () => {
    render(<StockDiscovery streamConfigured />);
    fireEvent.change(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { target: { value: "Reliance" } });
    fireEvent.click(await screen.findByText("Reliance Industries Ltd"));
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    const socket = MockWebSocket.instances[0];
    act(() => socket.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ type: "connected" }) })));
    expect(screen.getByText("Feed connected · awaiting provider tick")).toBeTruthy();
    act(() => socket.onmessage?.(new MessageEvent("message", { data: JSON.stringify({
      type: "quote",
      received_at: new Date().toISOString(),
      quote: {
        ...QUOTE_RESPONSE.quote,
        last_price: 1512.5,
        source: "Upstox Market Data Feed V3",
        delivery: "stream",
      },
    }) })));
    expect(await screen.findByText("Streaming connection")).toBeTruthy();
    expect(screen.getByText("Displayed quote: Streaming")).toBeTruthy();
    expect(screen.getByText("Last upstream message 0s ago")).toBeTruthy();
    expect(screen.getByText("₹1,512.50")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Close stock detail" }));
    expect(socket.sent).toEqual(["unsubscribe"]);
    expect(socket.closed).toBe(true);
  });

  it("does not retry when the backend marks streaming unavailable", async () => {
    render(<StockDiscovery streamConfigured />);
    fireEvent.change(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { target: { value: "Reliance" } });
    fireEvent.click(await screen.findByText("Reliance Industries Ltd"));
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    const socket = MockWebSocket.instances[0];
    act(() => socket.onmessage?.(new MessageEvent("message", { data: JSON.stringify({
      type: "unavailable",
      detail: "Upstox rejected the configured feed credential",
    }) })));
    act(() => socket.onclose?.());

    await act(async () => new Promise((resolve) => window.setTimeout(resolve, 600)));
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(screen.getByRole("alert").textContent).toContain("rejected the configured feed credential");
  });

  it("retries unexpected disconnects with bounded backoff", async () => {
    const view = render(<StockDiscovery streamConfigured />);
    fireEvent.change(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { target: { value: "Reliance" } });
    fireEvent.click(await screen.findByText("Reliance Industries Ltd"));
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    vi.useFakeTimers();

    act(() => MockWebSocket.instances[0].onclose?.());
    await act(async () => { await vi.advanceTimersByTimeAsync(499); });
    expect(MockWebSocket.instances).toHaveLength(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(MockWebSocket.instances).toHaveLength(2);

    act(() => MockWebSocket.instances[1].onclose?.());
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(MockWebSocket.instances).toHaveLength(3);
    act(() => MockWebSocket.instances[2].onclose?.());
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(MockWebSocket.instances).toHaveLength(4);
    act(() => MockWebSocket.instances[3].onclose?.());
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(MockWebSocket.instances).toHaveLength(4);

    view.unmount();
    vi.useRealTimers();
  });

  it("rehydrates watchlist identity from the server after page reload", async () => {
    mockedWatchlists.mockResolvedValue([makeWatchlist([RELIANCE])]);
    render(<StockDiscovery streamConfigured={false} />);
    expect(await screen.findByText("RELIANCE · NSE")).toBeTruthy();
    await waitFor(() => expect(mockedQuote).toHaveBeenCalledWith(RELIANCE.instrument_key, expect.any(AbortSignal)));
  });

  it("shows provider search errors, retries, and presents a real empty state", async () => {
    mockedSearch
      .mockRejectedValueOnce(new Error("Instrument discovery unavailable"))
      .mockResolvedValueOnce({ ...SEARCH_RESPONSE, instruments: [], page: { ...SEARCH_RESPONSE.page, total_pages: 0, total_records: 0 } });
    render(<StockDiscovery streamConfigured={false} />);
    fireEvent.change(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { target: { value: "Unknown Co" } });
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No supported equities matched this search.")).toBeTruthy();
    expect(mockedSearch).toHaveBeenCalledTimes(2);
  });

  it("keeps quote failures visible and supports manual recovery", async () => {
    mockedQuote.mockRejectedValueOnce(new Error("Selected stock quote unavailable"));
    render(<StockDiscovery streamConfigured={false} />);
    fireEvent.change(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { target: { value: "Reliance" } });
    fireEvent.click(await screen.findByText("Reliance Industries Ltd"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh quote" }));
    expect(await screen.findByText("₹1,500.00")).toBeTruthy();
    expect(mockedQuote).toHaveBeenCalledTimes(2);
  });

  it("ignores a late manual quote response after the user switches instruments", async () => {
    const tcs: MarketInstrument = {
      ...RELIANCE,
      instrument_key: "NSE_EQ|INE467B01029",
      trading_symbol: "TCS",
      name: "Tata Consultancy Services",
      isin: "INE467B01029",
    };
    mockedSearch.mockResolvedValue({ ...SEARCH_RESPONSE, instruments: [RELIANCE, tcs], page: { ...SEARCH_RESPONSE.page, total_records: 2 } });
    const lateReliance = deferred<MarketInstrumentQuoteResponse>();
    let relianceRequests = 0;
    mockedQuote.mockImplementation((key) => {
      if (key === RELIANCE.instrument_key) {
        relianceRequests += 1;
        return relianceRequests === 1 ? Promise.resolve(QUOTE_RESPONSE) : lateReliance.promise;
      }
      return Promise.resolve({
        ...QUOTE_RESPONSE,
        quote: { ...QUOTE_RESPONSE.quote, instrument_key: tcs.instrument_key, symbol: "TCS", name: tcs.name, isin: tcs.isin, last_price: 3200 },
      });
    });

    render(<StockDiscovery streamConfigured={false} />);
    fireEvent.change(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { target: { value: "Reliance" } });
    fireEvent.click(await screen.findByText("Reliance Industries Ltd"));
    expect(await screen.findByText("₹1,500.00")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh quote" }));
    await waitFor(() => expect(mockedQuote).toHaveBeenCalledTimes(2));

    fireEvent.click(screen.getByText("Tata Consultancy Services"));
    expect(await screen.findByText("₹3,200.00")).toBeTruthy();
    await act(async () => lateReliance.resolve({
      ...QUOTE_RESPONSE,
      quote: { ...QUOTE_RESPONSE.quote, last_price: 7777 },
    }));

    expect(screen.getByRole("heading", { name: "Tata Consultancy Services" })).toBeTruthy();
    expect(screen.getByText("₹3,200.00")).toBeTruthy();
    expect(screen.queryByText("₹7,777.00")).toBeNull();
  });

  it("ignores messages from the previous stock after a selection change", async () => {
    const tcs: MarketInstrument = {
      ...RELIANCE,
      instrument_key: "NSE_EQ|INE467B01029",
      trading_symbol: "TCS",
      name: "Tata Consultancy Services",
      isin: "INE467B01029",
    };
    mockedSearch.mockResolvedValue({ ...SEARCH_RESPONSE, instruments: [RELIANCE, tcs], page: { ...SEARCH_RESPONSE.page, total_records: 2 } });
    render(<StockDiscovery streamConfigured />);
    fireEvent.change(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { target: { value: "Reliance" } });
    fireEvent.click(await screen.findByText("Reliance Industries Ltd"));
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    const previousStockSocket = MockWebSocket.instances[0];

    fireEvent.click(screen.getByText("Tata Consultancy Services"));
    expect(await screen.findByRole("heading", { name: "Tata Consultancy Services" })).toBeTruthy();
    act(() => previousStockSocket.onmessage?.(new MessageEvent("message", { data: JSON.stringify({
      type: "quote",
      quote: { ...QUOTE_RESPONSE.quote, last_price: 7777, delivery: "stream" },
    }) })));

    expect(screen.queryByText("₹7,777.00")).toBeNull();
    expect(screen.getByText("₹1,500.00")).toBeTruthy();
  });

  it("ages a snapshot to stale when no newer feed message arrives", async () => {
    const now = new Date().toISOString();
    mockedQuote.mockResolvedValue({
      ...QUOTE_RESPONSE,
      fetched_at: now,
      quote: { ...QUOTE_RESPONSE.quote, source_timestamp: now, fetched_at: now, freshness: "fresh", delivery: "rest" },
    });
    const view = render(<StockDiscovery streamConfigured />);
    fireEvent.change(screen.getByPlaceholderText("Company name, symbol, or ISIN"), { target: { value: "Reliance" } });
    fireEvent.click(await screen.findByText("Reliance Industries Ltd"));
    expect(await screen.findByText("Fresh snapshot")).toBeTruthy();

    vi.useFakeTimers();
    vi.setSystemTime(new Date(Date.parse(now) + 301_000));
    await act(async () => { view.rerender(<StockDiscovery streamConfigured />); });
    expect(screen.getByText("Stale source data")).toBeTruthy();
    view.unmount();
    vi.useRealTimers();
  });
});
