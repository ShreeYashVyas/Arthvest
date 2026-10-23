export type MacroIndicator = {
  indicator: string;
  series_id: string;
  value_percent: number;
  observation_date: string;
  unit: string;
  source: string;
  source_url: string;
  retrieved_at: string;
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
    typeof data.retrieved_at === "string"
  );
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
