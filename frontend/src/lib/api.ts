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
