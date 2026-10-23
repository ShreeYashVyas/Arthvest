export type MacroIndicator = {
  indicator: string;
  series_id: string;
  value_percent: number;
  observation_date: string;
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
    typeof data.value_percent === "number" &&
    Number.isFinite(data.value_percent) &&
    typeof data.observation_date === "string" &&
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
