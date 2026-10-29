export type MacroIndicator = {
  indicator: string;
  series_id: string;
  value: number;
  observation_date: string;
  frequency: string;
  observation_age_days: number;
  freshness_status: "fresh" | "stale" | "in-progress";
  unit: string;
  source: string;
  source_url: string;
  retrieved_at: string;
  calculation?: string | null;
};

export type MacroOverviewItem = {
  key: string;
  category: string;
  status: "available" | "unavailable";
  data: MacroIndicator | null;
  error: string | null;
};

export type MacroOverview = {
  generated_at: string;
  available_count: number;
  total_count: number;
  indicators: MacroOverviewItem[];
};

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

function isMacroIndicator(value: unknown): value is MacroIndicator {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  return (
    typeof data.indicator === "string" &&
    typeof data.series_id === "string" &&
    typeof data.value === "number" &&
    Number.isFinite(data.value) &&
    typeof data.observation_date === "string" &&
    typeof data.frequency === "string" &&
    typeof data.observation_age_days === "number" &&
    Number.isInteger(data.observation_age_days) &&
    (data.freshness_status === "fresh" || data.freshness_status === "stale" || data.freshness_status === "in-progress") &&
    typeof data.unit === "string" &&
    typeof data.source === "string" &&
    typeof data.source_url === "string" &&
    typeof data.retrieved_at === "string" &&
    (data.calculation === undefined ||
      data.calculation === null ||
      typeof data.calculation === "string")
  );
}

function isMacroOverview(value: unknown): value is MacroOverview {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  if (
    typeof data.generated_at !== "string" ||
    typeof data.available_count !== "number" ||
    typeof data.total_count !== "number" ||
    !Array.isArray(data.indicators)
  ) {
    return false;
  }

  return data.indicators.every((item: unknown) => {
    if (typeof item !== "object" || item === null) return false;
    const entry = item as Record<string, unknown>;
    return (
      typeof entry.key === "string" &&
      typeof entry.category === "string" &&
      (entry.status === "available" || entry.status === "unavailable") &&
      (entry.data === null || isMacroIndicator(entry.data)) &&
      (entry.error === null || typeof entry.error === "string")
    );
  });
}

export async function fetchMacroOverview(
  signal?: AbortSignal,
): Promise<MacroOverview> {
  const response = await fetch(API_BASE_URL + "/api/macro/overview", {
    cache: "no-store",
    signal,
  });

  if (!response.ok) {
    throw new Error(
      response.status === 502
        ? "Macro data sources are temporarily unavailable. Please retry shortly."
        : "Macro API request failed (" + response.status + ").",
    );
  }

  const payload: unknown = await response.json();
  if (!isMacroOverview(payload)) {
    throw new Error("Macro API returned an unexpected response format.");
  }

  return payload;
}

export async function fetchFederalFundsRate(
  signal?: AbortSignal,
): Promise<MacroIndicator> {
  const response = await fetch(API_BASE_URL + "/api/macro/fed-funds", {
    cache: "no-store",
    signal,
  });

  if (!response.ok) {
    throw new Error(
      response.status === 502
        ? "FRED data is temporarily unavailable. Please retry shortly."
        : "Macro API request failed (" + response.status + ").",
    );
  }

  const payload: unknown = await response.json();
  if (!isMacroIndicator(payload)) {
    throw new Error("Macro API returned an unexpected response format.");
  }

  return payload;
}


export type MacroHistoryPoint = {
  observation_date: string;
  value: number;
};

export type MacroHistory = {
  generated_at: string;
  retrieved_at: string;
  key: string;
  indicator: string;
  series_id: string;
  unit: string;
  frequency: string;
  source: string;
  source_url: string;
  calculation: string;
  requested_limit: number;
  returned_count: number;
  points: MacroHistoryPoint[];
};

function isMacroHistory(value: unknown): value is MacroHistory {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  return (
    typeof data.generated_at === "string" &&
    typeof data.retrieved_at === "string" &&
    typeof data.key === "string" &&
    typeof data.indicator === "string" &&
    typeof data.series_id === "string" &&
    typeof data.unit === "string" &&
    typeof data.frequency === "string" &&
    typeof data.source === "string" &&
    typeof data.source_url === "string" &&
    typeof data.calculation === "string" &&
    typeof data.requested_limit === "number" &&
    typeof data.returned_count === "number" &&
    Array.isArray(data.points) &&
    data.points.every((point: unknown) => {
      if (typeof point !== "object" || point === null) return false;
      const item = point as Record<string, unknown>;
      return (
        typeof item.observation_date === "string" &&
        typeof item.value === "number" &&
        Number.isFinite(item.value)
      );
    })
  );
}

export async function fetchMacroHistory(
  key: string,
  limit = 12,
  signal?: AbortSignal,
): Promise<MacroHistory> {
  const allowedKeys = [
    "fed-funds",
    "us-inflation",
    "us-unemployment",
    "india-gdp-growth",
    "india-cpi-inflation-annual",
    "india-policy-uncertainty",
    "usd-inr",
    "india-reer",
  ];
  if (!allowedKeys.includes(key)) {
    throw new Error("Unsupported macro history key.");
  }

  const boundedLimit = Math.min(60, Math.max(1, Math.trunc(limit)));
  const response = await fetch(
    API_BASE_URL + "/api/macro/history/" + encodeURIComponent(key) +
      "?limit=" + boundedLimit,
    { cache: "no-store", signal },
  );

  if (!response.ok) {
    throw new Error("Historical macro observations are temporarily unavailable.");
  }

  const payload: unknown = await response.json();
  if (!isMacroHistory(payload)) {
    throw new Error("Macro history API returned an unexpected response format.");
  }
  return payload;
}


export type USMacroScoreComponent = {
  key: string;
  indicator: string;
  status: "available" | "stale" | "in-progress" | "unavailable";
  value_percent: number | null;
  observation_date: string | null;
  freshness_status: "fresh" | "stale" | "in-progress" | null;
  component_score: number | null;
  weight: number;
  weighted_points: number | null;
};

export type USMacroScore = {
  generated_at: string;
  available: boolean;
  score: number | null;
  label: "supportive" | "mixed" | "pressured" | "insufficient-data";
  provisional: boolean;
  weights: Record<string, number>;
  threshold_rules: Record<string, string[]>;
  components: USMacroScoreComponent[];
  methodology: string;
  limitations: string[];
  blockers: string[];
};

function isUSMacroScore(value: unknown): value is USMacroScore {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  return (
    typeof data.generated_at === "string" &&
    typeof data.available === "boolean" &&
    (data.score === null ||
      (typeof data.score === "number" && Number.isFinite(data.score))) &&
    ["supportive", "mixed", "pressured", "insufficient-data"].includes(
      String(data.label),
    ) &&
    typeof data.provisional === "boolean" &&
    typeof data.weights === "object" &&
    data.weights !== null &&
    typeof data.threshold_rules === "object" &&
    data.threshold_rules !== null &&
    Object.values(data.threshold_rules).every(
      (rules) => Array.isArray(rules) && rules.every((rule) => typeof rule === "string"),
    ) &&
    Array.isArray(data.components) &&
    typeof data.methodology === "string" &&
    Array.isArray(data.limitations) &&
    data.limitations.every((item: unknown) => typeof item === "string") &&
    Array.isArray(data.blockers) &&
    data.blockers.every((item: unknown) => typeof item === "string")
  );
}

export async function fetchUSMacroScore(
  signal?: AbortSignal,
): Promise<USMacroScore> {
  const response = await fetch(API_BASE_URL + "/api/macro/score/us-conditions", {
    cache: "no-store",
    signal,
  });

  if (!response.ok) {
    throw new Error("The provisional U.S. macro score is temporarily unavailable.");
  }

  const payload: unknown = await response.json();
  if (!isUSMacroScore(payload)) {
    throw new Error("Macro score API returned an unexpected response format.");
  }

  return payload;
}


export type MacroQualityItem = {
  key: string;
  status: "available" | "unavailable";
  freshness_status: "fresh" | "stale" | "in-progress" | null;
  observation_age_days: number | null;
  issue: string | null;
};

export type MacroQuality = {
  generated_at: string;
  total_count: number;
  available_count: number;
  unavailable_count: number;
  fresh_count: number;
  stale_count: number;
  in_progress_count: number;
  coverage_percent: number;
  quality_status: "good" | "partial" | "unavailable";
  note: string;
  indicators: MacroQualityItem[];
};

function isMacroQuality(value: unknown): value is MacroQuality {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  return (
    typeof data.generated_at === "string" &&
    typeof data.total_count === "number" &&
    typeof data.available_count === "number" &&
    typeof data.unavailable_count === "number" &&
    typeof data.fresh_count === "number" &&
    typeof data.stale_count === "number" &&
    typeof data.in_progress_count === "number" &&
    typeof data.coverage_percent === "number" &&
    Number.isFinite(data.coverage_percent) &&
    ["good", "partial", "unavailable"].includes(String(data.quality_status)) &&
    typeof data.note === "string" &&
    Array.isArray(data.indicators)
  );
}

export async function fetchMacroQuality(
  signal?: AbortSignal,
): Promise<MacroQuality> {
  const response = await fetch(API_BASE_URL + "/api/macro/quality", {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error("The macro data-quality summary is temporarily unavailable.");
  }
  const payload: unknown = await response.json();
  if (!isMacroQuality(payload)) {
    throw new Error("Data-quality API returned an unexpected response format.");
  }
  return payload;
}


export type MacroCatalogItem = {
  key: string;
  indicator: string;
  description: string;
  series_id: string;
  frequency: string;
  unit: string;
  source: string;
  source_url: string;
  calculation: string;
  freshness_threshold_days: number;
};

export type MacroCatalog = {
  generated_at: string;
  total_count: number;
  indicators: MacroCatalogItem[];
};

function isMacroCatalog(value: unknown): value is MacroCatalog {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  if (
    typeof data.generated_at !== "string" ||
    typeof data.total_count !== "number" ||
    !Array.isArray(data.indicators)
  ) {
    return false;
  }

  return data.indicators.every((item: unknown) => {
    if (typeof item !== "object" || item === null) return false;
    const entry = item as Record<string, unknown>;
    return (
      typeof entry.key === "string" &&
      typeof entry.indicator === "string" &&
      typeof entry.description === "string" &&
      typeof entry.series_id === "string" &&
      typeof entry.frequency === "string" &&
      typeof entry.unit === "string" &&
      typeof entry.source === "string" &&
      typeof entry.source_url === "string" &&
      typeof entry.calculation === "string" &&
      typeof entry.freshness_threshold_days === "number" &&
      Number.isInteger(entry.freshness_threshold_days)
    );
  });
}

export async function fetchMacroCatalog(
  signal?: AbortSignal,
): Promise<MacroCatalog> {
  const response = await fetch(API_BASE_URL + "/api/macro/catalog", {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error("The macro indicator catalog is temporarily unavailable.");
  }
  const payload: unknown = await response.json();
  if (!isMacroCatalog(payload)) {
    throw new Error("Macro catalog API returned an unexpected response format.");
  }
  return payload;
}


export type HistoricalAnalyticsDirection =
  | "higher"
  | "lower"
  | "flat"
  | "insufficient-history";

export type HistoricalAnalyticsSummary = {
  oldest_value: number | null;
  latest_value: number | null;
  absolute_change: number | null;
  relative_change_percent: number | null;
  direction: HistoricalAnalyticsDirection;
  mean: number | null;
  minimum: number | null;
  maximum: number | null;
  population_standard_deviation: number | null;
};

export type HistoricalAnalytics = {
  generated_at: string;
  key: string;
  indicator: string;
  series_id: string;
  unit: string;
  change_unit: string;
  frequency: string;
  source: string;
  source_url: string;
  calculation: string;
  requested_limit: number;
  returned_count: number;
  period_start: string | null;
  period_end: string | null;
  summary: HistoricalAnalyticsSummary;
  points: MacroHistoryPoint[];
  limitations: string[];
};

function isNullableFiniteNumber(value: unknown): value is number | null {
  return value === null || (
    typeof value === "number" && Number.isFinite(value)
  );
}

function isHistoricalAnalytics(value: unknown): value is HistoricalAnalytics {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  if (
    typeof data.generated_at !== "string" ||
    typeof data.key !== "string" ||
    typeof data.indicator !== "string" ||
    typeof data.series_id !== "string" ||
    typeof data.unit !== "string" ||
    typeof data.change_unit !== "string" ||
    typeof data.frequency !== "string" ||
    typeof data.source !== "string" ||
    typeof data.source_url !== "string" ||
    typeof data.calculation !== "string" ||
    typeof data.requested_limit !== "number" ||
    typeof data.returned_count !== "number" ||
    !(data.period_start === null || typeof data.period_start === "string") ||
    !(data.period_end === null || typeof data.period_end === "string") ||
    typeof data.summary !== "object" ||
    data.summary === null ||
    !Array.isArray(data.points) ||
    !Array.isArray(data.limitations) ||
    !data.limitations.every((item: unknown) => typeof item === "string")
  ) return false;

  const summary = data.summary as Record<string, unknown>;
  return (
    isNullableFiniteNumber(summary.oldest_value) &&
    isNullableFiniteNumber(summary.latest_value) &&
    isNullableFiniteNumber(summary.absolute_change) &&
    isNullableFiniteNumber(summary.relative_change_percent) &&
    ["higher", "lower", "flat", "insufficient-history"].includes(String(summary.direction)) &&
    isNullableFiniteNumber(summary.mean) &&
    isNullableFiniteNumber(summary.minimum) &&
    isNullableFiniteNumber(summary.maximum) &&
    isNullableFiniteNumber(summary.population_standard_deviation) &&
    data.points.every((point: unknown) => {
      if (typeof point !== "object" || point === null) return false;
      const item = point as Record<string, unknown>;
      return typeof item.observation_date === "string" &&
        typeof item.value === "number" && Number.isFinite(item.value);
    })
  );
}

export async function fetchHistoricalAnalytics(
  key: string,
  limit = 12,
  signal?: AbortSignal,
): Promise<HistoricalAnalytics> {
  const allowedKeys = [
    "fed-funds",
    "us-inflation",
    "us-unemployment",
    "india-gdp-growth",
    "india-cpi-inflation-annual",
    "india-policy-uncertainty",
    "usd-inr",
    "india-reer",
  ];
  if (!allowedKeys.includes(key)) {
    throw new Error("Unsupported macro analytics key.");
  }

  const boundedLimit = Math.min(60, Math.max(2, Math.trunc(limit)));
  const response = await fetch(
    API_BASE_URL + "/api/macro/analytics/" + encodeURIComponent(key) +
      "?limit=" + boundedLimit,
    { cache: "no-store", signal },
  );
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null &&
      "detail" in payload && typeof (payload as { detail?: unknown }).detail === "string"
      ? (payload as { detail: string }).detail
      : null;
    throw new Error(detail ?? "Historical analytics are temporarily unavailable.");
  }
  if (!isHistoricalAnalytics(payload)) {
    throw new Error("Historical analytics API returned an unexpected response format.");
  }
  return payload;
}


export type MacroComparisonStatus =
  | "available"
  | "insufficient-history"
  | "non-positive-base-value";

export type MacroComparisonPoint = {
  observation_date: string;
  raw_value: number;
  indexed_value: number;
};

export type MacroComparisonSeries = {
  key: string;
  indicator: string;
  series_id: string;
  unit: string;
  frequency: string;
  source: string;
  source_url: string;
  status: MacroComparisonStatus;
  reason: string | null;
  period_start: string | null;
  period_end: string | null;
  observation_count: number;
  base_value: number | null;
  latest_value: number | null;
  relative_change_percent: number | null;
  points: MacroComparisonPoint[];
};

export type MacroComparison = {
  generated_at: string;
  years: number;
  window_start: string;
  window_end: string;
  requested_indicators: string[];
  available_count: number;
  series: MacroComparisonSeries[];
  methodology: string;
  limitations: string[];
};

function isMacroComparison(value: unknown): value is MacroComparison {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  if (
    typeof data.generated_at !== "string" ||
    typeof data.years !== "number" ||
    typeof data.window_start !== "string" ||
    typeof data.window_end !== "string" ||
    !Array.isArray(data.requested_indicators) ||
    !data.requested_indicators.every((key: unknown) => typeof key === "string") ||
    typeof data.available_count !== "number" ||
    !Array.isArray(data.series) ||
    typeof data.methodology !== "string" ||
    !Array.isArray(data.limitations) ||
    !data.limitations.every((item: unknown) => typeof item === "string")
  ) return false;

  return data.series.every((rawSeries: unknown) => {
    if (typeof rawSeries !== "object" || rawSeries === null) return false;
    const series = rawSeries as Record<string, unknown>;
    if (
      typeof series.key !== "string" ||
      typeof series.indicator !== "string" ||
      typeof series.series_id !== "string" ||
      typeof series.unit !== "string" ||
      typeof series.frequency !== "string" ||
      typeof series.source !== "string" ||
      typeof series.source_url !== "string" ||
      !["available", "insufficient-history", "non-positive-base-value"].includes(String(series.status)) ||
      !(series.reason === null || typeof series.reason === "string") ||
      !(series.period_start === null || typeof series.period_start === "string") ||
      !(series.period_end === null || typeof series.period_end === "string") ||
      typeof series.observation_count !== "number" ||
      !isNullableFiniteNumber(series.base_value) ||
      !isNullableFiniteNumber(series.latest_value) ||
      !isNullableFiniteNumber(series.relative_change_percent) ||
      !Array.isArray(series.points)
    ) return false;

    return series.points.every((rawPoint: unknown) => {
      if (typeof rawPoint !== "object" || rawPoint === null) return false;
      const point = rawPoint as Record<string, unknown>;
      return typeof point.observation_date === "string" &&
        typeof point.raw_value === "number" && Number.isFinite(point.raw_value) &&
        typeof point.indexed_value === "number" && Number.isFinite(point.indexed_value);
    });
  });
}

export async function fetchMacroComparison(
  indicators: string[],
  years = 5,
  signal?: AbortSignal,
): Promise<MacroComparison> {
  const allowedKeys = [
    "fed-funds",
    "us-inflation",
    "us-unemployment",
    "india-gdp-growth",
    "india-cpi-inflation-annual",
    "india-policy-uncertainty",
    "usd-inr",
    "india-reer",
  ];
  if (indicators.length < 2 || indicators.length > 5 ||
      new Set(indicators).size !== indicators.length ||
      !indicators.every((key) => allowedKeys.includes(key))) {
    throw new Error("Select between 2 and 5 different supported indicators.");
  }
  if (![1, 3, 5, 10].includes(years)) {
    throw new Error("Comparison window must be 1, 3, 5, or 10 years.");
  }

  const params = new URLSearchParams({
    indicators: indicators.join(","),
    years: String(years),
  });
  const response = await fetch(API_BASE_URL + "/api/macro/compare?" + params.toString(), {
    cache: "no-store",
    signal,
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null &&
      "detail" in payload && typeof (payload as { detail?: unknown }).detail === "string"
      ? (payload as { detail: string }).detail
      : null;
    throw new Error(detail ?? "Macro comparison is temporarily unavailable.");
  }
  if (!isMacroComparison(payload)) {
    throw new Error("Macro comparison API returned an unexpected response format.");
  }
  return payload;
}


export type MacroStorageStatus = {
  enabled: boolean;
  available: boolean;
  backend: string;
  observation_count: number | null;
  revision_count: number | null;
  source_check_count: number | null;
  last_check_at: string | null;
  database_status: "connected" | "disconnected" | "authentication_failure" | "configuration_missing" | "configuration_invalid" | "schema_error";
  schema_status: "current" | "not_checked" | "error";
  schema_version: number | null;
  market_history_status: "never_synchronized" | "initial_sync_pending" | "synchronizing" | "synchronized" | "stale" | "synchronization_failed" | "partially_synchronized";
  instruments_tracked: number | null;
  candles_by_interval: Record<string, number>;
  candle_count: number | null;
  latest_stored_candle_at: string | null;
  coverage_start: string | null;
  coverage_end: string | null;
  latest_upstream_fetch_at: string | null;
  last_successful_sync_at: string | null;
  last_attempted_sync_at: string | null;
  last_failure_category: string | null;
  catalogue_sync_status: string;
  catalogue_last_successful_sync_at: string | null;
  note: string;
};

export type MacroSourceCheck = {
  indicator_key: string | null;
  series_id: string;
  checked_at: string;
  status: "success" | "failure";
  observation_count: number | null;
  latest_observation_date: string | null;
  latest_source_value: number | null;
  elapsed_ms: number | null;
  error_code: string | null;
};

export type MacroSourceChecks = {
  count: number;
  checks: MacroSourceCheck[];
};

function isNullableCount(value: unknown): value is number | null {
  return value === null || (
    typeof value === "number" && Number.isInteger(value) && value >= 0
  );
}

function isMacroStorageStatus(value: unknown): value is MacroStorageStatus {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  return typeof data.enabled === "boolean" &&
    typeof data.available === "boolean" &&
    typeof data.backend === "string" &&
    typeof data.database_status === "string" &&
    typeof data.schema_status === "string" &&
    typeof data.market_history_status === "string" &&
    isNullableCount(data.schema_version) &&
    isNullableCount(data.instruments_tracked) &&
    isNullableCount(data.candle_count) &&
    typeof data.candles_by_interval === "object" && data.candles_by_interval !== null &&
    ["latest_stored_candle_at", "coverage_start", "coverage_end", "latest_upstream_fetch_at", "last_successful_sync_at", "last_attempted_sync_at", "last_failure_category", "catalogue_last_successful_sync_at"].every((key) => data[key] === null || typeof data[key] === "string") &&
    typeof data.catalogue_sync_status === "string" &&
    isNullableCount(data.observation_count) &&
    isNullableCount(data.revision_count) &&
    isNullableCount(data.source_check_count) &&
    (data.last_check_at === null || typeof data.last_check_at === "string") &&
    typeof data.note === "string";
}

export async function fetchMacroStorageStatus(
  signal?: AbortSignal,
): Promise<MacroStorageStatus> {
  const response = await fetch(API_BASE_URL + "/api/macro/storage", {
    cache: "no-store",
    signal,
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error("Database status is temporarily unavailable.");
  }
  if (!isMacroStorageStatus(payload)) {
    throw new Error("Database status API returned an unexpected response format.");
  }
  return payload;
}

function isMacroSourceChecks(value: unknown): value is MacroSourceChecks {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  if (typeof data.count !== "number" || !Number.isInteger(data.count) ||
      !Array.isArray(data.checks)) return false;

  return data.checks.every((rawCheck: unknown) => {
    if (typeof rawCheck !== "object" || rawCheck === null) return false;
    const check = rawCheck as Record<string, unknown>;
    return (check.indicator_key === null || typeof check.indicator_key === "string") &&
      typeof check.series_id === "string" &&
      typeof check.checked_at === "string" &&
      (check.status === "success" || check.status === "failure") &&
      isNullableCount(check.observation_count) &&
      (check.latest_observation_date === null || typeof check.latest_observation_date === "string") &&
      (check.latest_source_value === null ||
        (typeof check.latest_source_value === "number" && Number.isFinite(check.latest_source_value))) &&
      (check.elapsed_ms === null ||
        (typeof check.elapsed_ms === "number" && Number.isInteger(check.elapsed_ms))) &&
      (check.error_code === null || typeof check.error_code === "string");
  });
}

export async function fetchMacroSourceChecks(
  limit = 24,
  signal?: AbortSignal,
): Promise<MacroSourceChecks> {
  const boundedLimit = Math.min(100, Math.max(1, Math.trunc(limit)));
  const response = await fetch(
    API_BASE_URL + "/api/macro/source-checks?limit=" + boundedLimit,
    { cache: "no-store", signal },
  );
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null &&
      "detail" in payload && typeof (payload as { detail?: unknown }).detail === "string"
      ? (payload as { detail: string }).detail
      : null;
    throw new Error(detail ?? "Recent source checks are temporarily unavailable.");
  }
  if (!isMacroSourceChecks(payload)) {
    throw new Error("Source-check API returned an unexpected response format.");
  }
  return payload;
}


export type MacroObservationRevision = {
  series_id: string;
  observation_date: string;
  previous_value: number;
  revised_value: number;
  detected_at: string;
  retrieved_at: string;
};

export type MacroRevisions = {
  key: string;
  series_id: string;
  count: number;
  revisions: MacroObservationRevision[];
};

function isMacroRevisions(value: unknown): value is MacroRevisions {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  if (
    typeof data.key !== "string" ||
    typeof data.series_id !== "string" ||
    typeof data.count !== "number" ||
    !Number.isInteger(data.count) ||
    !Array.isArray(data.revisions)
  ) return false;

  return data.revisions.every((rawRevision: unknown) => {
    if (typeof rawRevision !== "object" || rawRevision === null) return false;
    const revision = rawRevision as Record<string, unknown>;
    return typeof revision.series_id === "string" &&
      typeof revision.observation_date === "string" &&
      typeof revision.previous_value === "number" && Number.isFinite(revision.previous_value) &&
      typeof revision.revised_value === "number" && Number.isFinite(revision.revised_value) &&
      typeof revision.detected_at === "string" &&
      typeof revision.retrieved_at === "string";
  });
}

export async function fetchMacroRevisions(
  key: string,
  limit = 20,
  signal?: AbortSignal,
): Promise<MacroRevisions> {
  const allowedKeys = [
    "fed-funds",
    "us-inflation",
    "us-unemployment",
    "india-gdp-growth",
    "india-cpi-inflation-annual",
    "india-policy-uncertainty",
    "usd-inr",
    "india-reer",
  ];
  if (!allowedKeys.includes(key)) {
    throw new Error("Unsupported macro revision key.");
  }

  const boundedLimit = Math.min(100, Math.max(1, Math.trunc(limit)));
  const response = await fetch(
    API_BASE_URL + "/api/macro/revisions/" + encodeURIComponent(key) +
      "?limit=" + boundedLimit,
    { cache: "no-store", signal },
  );
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null &&
      "detail" in payload && typeof (payload as { detail?: unknown }).detail === "string"
      ? (payload as { detail: string }).detail
      : null;
    throw new Error(detail ?? "Macro revision history is temporarily unavailable.");
  }
  if (!isMacroRevisions(payload)) {
    throw new Error("Macro revision API returned an unexpected response format.");
  }
  return payload;
}

export type MarketProviderStatus = {
  provider_setting: "auto" | "upstox" | "yahoo";
  provider: string;
  configured: boolean;
  stream_configured: boolean;
  connection_state: "connecting" | "connected" | "reconnecting" | "unauthorized" | "unavailable" | "disconnected";
  last_authorized_at: string | null;
  last_connected_at: string | null;
  last_message_received_at: string | null;
  last_tick_received_at: string | null;
  last_source_timestamp: string | null;
  upstream_message_count: number;
  subscribed_instrument_count: number;
  reconnect_attempts: number;
  stream_error_category: string | null;
  stream_failure_reason: string | null;
  note: string;
  cache_seconds: number;
  auto_refresh_seconds: number;
};

export type MarketQuote = {
  key: string;
  symbol: string;
  instrument_id: string;
  provider_symbol: string | null;
  last_price: number | null;
  change: number | null;
  change_percent: number | null;
  currency: string | null;
  source: string;
  source_timestamp: string | null;
  fetched_at: string;
  freshness: "fresh" | "delayed" | "stale" | "unknown";
  status: "available" | "unavailable";
};

export type MarketQuotesResponse = {
  provider_setting: "auto" | "upstox" | "yahoo";
  provider: string;
  source_url: string;
  status: "available" | "partial";
  fetched_at: string;
  available_count: number;
  total_count: number;
  cache_seconds: number;
  cached: boolean;
  quotes: MarketQuote[];
};

function isMarketProviderStatus(value: unknown): value is MarketProviderStatus {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  return ["auto", "upstox", "yahoo"].includes(String(data.provider_setting)) &&
    typeof data.provider === "string" && typeof data.configured === "boolean" &&
    typeof data.stream_configured === "boolean" &&
    ["connecting", "connected", "reconnecting", "unauthorized", "unavailable", "disconnected"].includes(String(data.connection_state)) &&
    (data.last_authorized_at === null || typeof data.last_authorized_at === "string") &&
    (data.last_connected_at === null || typeof data.last_connected_at === "string") &&
    (data.last_message_received_at === null || typeof data.last_message_received_at === "string") &&
    (data.last_tick_received_at === null || typeof data.last_tick_received_at === "string") &&
    (data.last_source_timestamp === null || typeof data.last_source_timestamp === "string") &&
    typeof data.upstream_message_count === "number" &&
    typeof data.subscribed_instrument_count === "number" && typeof data.reconnect_attempts === "number" &&
    (data.stream_error_category === null || typeof data.stream_error_category === "string") &&
    (data.stream_failure_reason === null || typeof data.stream_failure_reason === "string") &&
    typeof data.note === "string" && typeof data.cache_seconds === "number" &&
    typeof data.auto_refresh_seconds === "number";
}

function isMarketQuote(value: unknown): value is MarketQuote {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  const nullableNumber = (item: unknown) => item === null ||
    (typeof item === "number" && Number.isFinite(item));
  const nullableString = (item: unknown) => item === null || typeof item === "string";
  return typeof data.key === "string" && typeof data.symbol === "string" &&
    typeof data.instrument_id === "string" && nullableString(data.provider_symbol) &&
    nullableNumber(data.last_price) && nullableNumber(data.change) &&
    nullableNumber(data.change_percent) && nullableString(data.currency) &&
    typeof data.source === "string" && nullableString(data.source_timestamp) &&
    typeof data.fetched_at === "string" &&
    ["fresh", "delayed", "stale", "unknown"].includes(String(data.freshness)) &&
    ["available", "unavailable"].includes(String(data.status));
}

function isMarketQuotesResponse(value: unknown): value is MarketQuotesResponse {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Record<string, unknown>;
  return ["auto", "upstox", "yahoo"].includes(String(data.provider_setting)) &&
    typeof data.provider === "string" && typeof data.source_url === "string" &&
    ["available", "partial"].includes(String(data.status)) &&
    typeof data.fetched_at === "string" && typeof data.available_count === "number" &&
    typeof data.total_count === "number" && typeof data.cache_seconds === "number" &&
    typeof data.cached === "boolean" && Array.isArray(data.quotes) &&
    data.quotes.every(isMarketQuote);
}

async function marketApiError(response: Response, fallback: string): Promise<Error> {
  const payload: unknown = await response.json().catch(() => null);
  const detail = typeof payload === "object" && payload !== null &&
      "detail" in payload && typeof (payload as { detail?: unknown }).detail === "string"
    ? (payload as { detail: string }).detail
    : fallback;
  return new Error(detail);
}

export async function fetchMarketProviderStatus(
  signal?: AbortSignal,
): Promise<MarketProviderStatus> {
  const response = await fetch(API_BASE_URL + "/api/market/status", {
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw await marketApiError(response, "Market provider status is unavailable.");
  const payload: unknown = await response.json().catch(() => null);
  if (!isMarketProviderStatus(payload)) {
    throw new Error("Market provider status returned an unexpected response format.");
  }
  return payload;
}

export async function fetchMarketQuotes(
  symbols?: string[],
  signal?: AbortSignal,
): Promise<MarketQuotesResponse> {
  const query = symbols?.length
    ? "?symbols=" + encodeURIComponent(symbols.join(","))
    : "";
  const response = await fetch(API_BASE_URL + "/api/market/quotes" + query, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw await marketApiError(response, "Market quotes are unavailable.");
  const payload: unknown = await response.json().catch(() => null);
  if (!isMarketQuotesResponse(payload)) {
    throw new Error("Market quote API returned an unexpected response format.");
  }
  return payload;
}

export type MarketInstrument = {
  instrument_key: string;
  trading_symbol: string;
  name: string;
  short_name: string | null;
  exchange: "NSE" | "BSE";
  segment: "NSE_EQ" | "BSE_EQ";
  instrument_type: string;
  isin: string | null;
  lot_size: number | null;
  tick_size: number | null;
  source: string;
  catalogue_updated_at: string | null;
};

export type MarketWatchlist = {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
  instruments: MarketInstrument[];
};

async function parseWatchlistResponse(response: Response): Promise<MarketWatchlist> {
  if (!response.ok) throw await marketApiError(response, "Watchlist changes could not be saved.");
  const payload: unknown = await response.json().catch(() => null);
  if (typeof payload !== "object" || payload === null ||
      typeof (payload as { id?: unknown }).id !== "number" ||
      typeof (payload as { name?: unknown }).name !== "string" ||
      !Array.isArray((payload as { instruments?: unknown }).instruments)) {
    throw new Error("Watchlist API returned an unexpected response format.");
  }
  return payload as MarketWatchlist;
}

export async function fetchWatchlists(signal?: AbortSignal): Promise<MarketWatchlist[]> {
  const response = await fetch(API_BASE_URL + "/api/watchlists", { cache: "no-store", signal });
  if (!response.ok) throw await marketApiError(response, "Saved watchlists are unavailable.");
  const payload: unknown = await response.json().catch(() => null);
  if (typeof payload !== "object" || payload === null ||
      !Array.isArray((payload as { watchlists?: unknown }).watchlists)) {
    throw new Error("Watchlist API returned an unexpected response format.");
  }
  return (payload as { watchlists: MarketWatchlist[] }).watchlists;
}

export async function createWatchlist(name: string): Promise<MarketWatchlist> {
  return parseWatchlistResponse(await fetch(API_BASE_URL + "/api/watchlists", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
  }));
}

export async function renameWatchlist(id: number, name: string): Promise<MarketWatchlist> {
  return parseWatchlistResponse(await fetch(API_BASE_URL + "/api/watchlists/" + id, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
  }));
}

export async function deleteWatchlist(id: number): Promise<void> {
  const response = await fetch(API_BASE_URL + "/api/watchlists/" + id, { method: "DELETE" });
  if (!response.ok) throw await marketApiError(response, "The watchlist could not be deleted.");
}

export async function replaceWatchlistEntries(id: number, instrumentKeys: string[]): Promise<MarketWatchlist> {
  return parseWatchlistResponse(await fetch(API_BASE_URL + "/api/watchlists/" + id + "/entries", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instrument_keys: instrumentKeys }),
  }));
}

export type InstrumentSearchResponse = {
  query: string;
  exchange: "ALL" | "NSE" | "BSE";
  instruments: MarketInstrument[];
  page: { page_number: number; total_pages: number; records: number; total_records: number };
  source: string;
  catalogue_updated_at: string | null;
};

export type MarketInstrumentQuote = {
  instrument_key: string;
  symbol: string;
  name: string;
  exchange: string;
  segment: string;
  instrument_type: string;
  isin: string | null;
  last_price: number | null;
  change: number | null;
  change_percent: number | null;
  previous_close: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  currency: string | null;
  source: string;
  delivery?: "stream" | "rest";
  source_timestamp: string | null;
  fetched_at: string;
  freshness: "fresh" | "stale" | "unknown";
  status: "available" | "unavailable";
};

export type MarketInstrumentQuoteResponse = {
  provider: string;
  source_url: string;
  fetched_at: string;
  cached: boolean;
  quote: MarketInstrumentQuote;
};

export type MarketCandle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type MarketHistoryResponse = {
  instrument_key: string;
  symbol: string;
  exchange: string;
  provider: string;
  unit: string;
  interval: number;
  from_date: string;
  to_date: string;
  fetched_at: string;
  candles: MarketCandle[];
  technical_indicators?: {
    status: "available" | "insufficient_history";
    input_candle_count: number;
    latest_candle_at: string | null;
    source: string;
    values: Record<string, number | null>;
    periods: Record<string, number | number[]>;
  };
};

export async function searchMarketInstruments(
  query: string,
  exchange: "ALL" | "NSE" | "BSE" = "ALL",
  page = 1,
  signal?: AbortSignal,
): Promise<InstrumentSearchResponse> {
  const params = new URLSearchParams({ q: query, exchange, page: String(page), records: "20" });
  const response = await fetch(API_BASE_URL + "/api/market/instruments/search?" + params, {
    cache: "no-store", signal,
  });
  if (!response.ok) throw await marketApiError(response, "Instrument search is unavailable.");
  const payload: unknown = await response.json().catch(() => null);
  if (typeof payload !== "object" || payload === null ||
      !Array.isArray((payload as { instruments?: unknown }).instruments) ||
      typeof (payload as { source?: unknown }).source !== "string") {
    throw new Error("Instrument search returned an unexpected response format.");
  }
  return payload as InstrumentSearchResponse;
}

export async function fetchInstrumentQuote(
  instrumentKey: string,
  signal?: AbortSignal,
): Promise<MarketInstrumentQuoteResponse> {
  const response = await fetch(API_BASE_URL + "/api/market/instruments/" +
    encodeURIComponent(instrumentKey) + "/quote", { cache: "no-store", signal });
  if (!response.ok) throw await marketApiError(response, "The selected instrument quote is unavailable.");
  const payload: unknown = await response.json().catch(() => null);
  if (typeof payload !== "object" || payload === null ||
      typeof (payload as { quote?: unknown }).quote !== "object") {
    throw new Error("Instrument quote returned an unexpected response format.");
  }
  return payload as MarketInstrumentQuoteResponse;
}

export async function fetchInstrumentHistory(
  instrumentKey: string,
  signal?: AbortSignal,
  range: "1M" | "3M" | "1Y" | "5Y" = "1Y",
): Promise<MarketHistoryResponse> {
  const to = new Date();
  const from = new Date(to);
  const daysByRange = { "1M": 30, "3M": 90, "1Y": 365, "5Y": 1825 };
  from.setDate(from.getDate() - daysByRange[range]);
  const date = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
  const params = new URLSearchParams({ unit: "days", interval: "1", from_date: date(from), to_date: date(to) });
  const response = await fetch(API_BASE_URL + "/api/market/instruments/" +
    encodeURIComponent(instrumentKey) + "/history?" + params, { cache: "no-store", signal });
  if (!response.ok) throw await marketApiError(response, "Historical candles are unavailable.");
  const payload: unknown = await response.json().catch(() => null);
  if (typeof payload !== "object" || payload === null ||
      !Array.isArray((payload as { candles?: unknown }).candles)) {
    throw new Error("Historical data returned an unexpected response format.");
  }
  return payload as MarketHistoryResponse;
}

export function marketStreamUrl(instrumentKey: string): string {
  const websocketBase = API_BASE_URL.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
  return websocketBase + "/api/market/stream/" + encodeURIComponent(instrumentKey);
}
