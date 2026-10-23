# Macro Data Dictionary

This document describes the current Phase 1 data inputs. Source readings are observations from published series, not streaming prices or personalized investment advice.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Service health |
| GET | `/api/macro/catalog` | Definitions, units, source, frequency, methodology and freshness thresholds |
| GET | `/api/macro/overview` | Best-effort snapshot of all configured indicators |
| GET | `/api/macro/quality` | Coverage and freshness summary |
| GET | `/api/macro/history/{indicator_key}?limit=12` | Up to 60 latest historical observations |
| GET | `/api/macro/fed-funds` | Federal Funds Rate compatibility endpoint |
| GET | `/api/macro/score/us-conditions` | Provisional U.S.-only macro conditions subscore |
| GET | `/api/macro/storage` | Optional database readiness and archive counts |
| GET | `/api/macro/archive/{indicator_key}` | Archived source-native values (requires `DATABASE_URL`) |
| GET | `/api/macro/revisions/{indicator_key}` | Detected upstream value revisions (requires `DATABASE_URL`) |
| GET | `/api/macro/source-checks` | Recent upstream fetch outcomes (requires `DATABASE_URL`)

## Configured indicators

| Key | Series | Unit | Frequency | Freshness threshold |
|---|---|---|---|---:|
| `fed-funds` | FEDFUNDS | Percent | Monthly | 120 days |
| `us-inflation` | CPIAUCSL | Percent year over year (calculated) | Monthly | 100 days |
| `us-unemployment` | UNRATE | Percent, seasonally adjusted | Monthly | 100 days |
| `india-gdp-growth` | INDGDPRQPSMEI | Percent year over year | Quarterly | 240 days |
| `india-cpi-inflation-annual` | FPCPITOTLZGIND | Percent (annual) | Annual | 550 days |
| `india-policy-uncertainty` | INDEPUINDXM | Index | Monthly | 120 days |
| `usd-inr` | DEXINUS | INR per USD | Daily, excluding non-publishing days | 7 days |
| `india-reer` | CCRETT01INM661N | Index (2015=100) | Monthly | 100 days |

Series metadata and links are returned dynamically by `/api/macro/catalog`.

## Manual upstream source sanity check

The public FRED series pages below were checked on **2026-10-23** to confirm that each configured series ID resolves to the expected macroeconomic concept and has a recent published observation. This is a manual source-page check, not an automated runtime guarantee; the application still validates every fetched CSV response and reports unavailable or stale data rather than assuming a source is healthy.

| Arthvest key | Upstream series page | Latest observation shown during check |
|---|---|---|
| `fed-funds` | [FEDFUNDS](https://fred.stlouisfed.org/series/FEDFUNDS) | September 2026: 3.75% |
| `us-inflation` | [CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL) | September 2026: 3.72% year-over-year, calculated by Arthvest |
| `us-unemployment` | [UNRATE](https://fred.stlouisfed.org/series/UNRATE) | September 2026: 4.2% |
| `india-gdp-growth` | [INDGDPRQPSMEI](https://fred.stlouisfed.org/series/INDGDPRQPSMEI) | Q2 2026: 8.098% year-over-year |
| `india-cpi-inflation-annual` | [FPCPITOTLZGIND](https://fred.stlouisfed.org/series/FPCPITOTLZGIND) | 2025: 2.399% annual inflation |
| `india-policy-uncertainty` | [INDEPUINDXM](https://fred.stlouisfed.org/series/INDEPUINDXM) | September 2026: 184.6 index points |
| `usd-inr` | [DEXINUS](https://fred.stlouisfed.org/series/DEXINUS) | October 16, 2026: ₹94.96 per USD |
| `india-reer` | [CCRETT01INM661N](https://fred.stlouisfed.org/series/CCRETT01INM661N) | September 2026: 92.37 index points (base 2015=100) |


## Archived historical analytics

`GET /api/macro/analytics/{indicator_key}?limit=12` summarizes a window of 2–60 archived display observations. Output includes oldest/latest value, absolute change in the displayed unit (percentage points for percentage-based indicators), relative mathematical change, direction, mean, minimum, maximum, and population standard deviation. The direction labels only describe whether values rose, fell, or stayed flat; they do not say whether a move is economically good or bad. For `us-inflation`, archived raw CPI index levels are converted into year-over-year inflation points before analysis. The endpoint requires a reachable configured database and returns no live-source fallback: that makes it clear the analysis is based on saved history, not just today's upstream response. The result is descriptive, not a forecast or validated regime model.

## Calculation rules

- U.S. CPI inflation is calculated as the 12-month percentage change in `CPIAUCSL`, using the same observation month in the prior year.
- The U.S. unemployment rate, effective federal funds rate, India GDP growth, annual India CPI inflation, India policy-uncertainty index, INR/USD exchange rate and Indian REER are displayed from the latest non-missing observation.
- India CPI inflation in this catalog is an annual World Bank series; it must not be mistaken for India's monthly CPI release.
- Historical CPI inflation points are calculated for each month where a matching observation from 12 months earlier is available.
- Missing, invalid and non-finite observations are not silently converted to zero.
- Only `fresh` completed observations are eligible for the provisional U.S. score; `stale` and `in-progress` inputs cause the score to be withheld.
- Freshness is measured from the end of the represented observation period, not the retrieval time: month-end for monthly data, quarter-end for quarterly data, year-end for annual data, and the observation date for daily data. The original source observation date is preserved in the API. When the source timestamp belongs to the current period, its period-age is clamped to zero and the observation is labelled `in-progress` until that period ends; source dates themselves must not be in the future.
- The annual India CPI source uses a year-start timestamp for an annual observation; its freshness age is therefore computed from that year's end. The 550-day threshold allows for annual release timing, but remains a provisional operational check rather than a statement about economic significance.
- Freshness thresholds are provisional operational checks, not statements about economic significance. The data-quality endpoint reports `fresh`, `stale`, `in-progress` and unavailable inputs separately.
- FRED observations may be revised. Arthvest caches each fetched series in-process for 15 minutes. If `DATABASE_URL` is configured, the service also archives fetched source observations by series and observation date, logs each upstream fetch outcome, and retains revision records whenever an existing source value changes. Re-fetching unchanged values updates last-seen metadata but does not create a revision. The archive stores source-native values (including CPIAUCSL index levels), separate from derived display calculations. If the database is unset or temporarily unavailable, live macro responses continue; persistence errors are logged rather than converting a successful feed into an API failure.

## Provisional U.S. subscore

The score currently combines only three U.S. observations:

| Component | Weight |
|---|---:|
| Federal Funds Effective Rate | 25% |
| U.S. CPI inflation | 45% |
| U.S. unemployment rate | 30% |

Fixed threshold bands translate each input into a 0–100 component score and calculate a weighted average. The score is withheld if a required observation is unavailable, invalid or stale.

Exact prototype bands returned by the API:

| Component | Input threshold | Component score |
|---|---|---:|
| Federal Funds Rate | value <= 2.00% | 85 |
| Federal Funds Rate | > 2.00% and <= 3.50% | 75 |
| Federal Funds Rate | > 3.50% and <= 4.50% | 60 |
| Federal Funds Rate | > 4.50% and <= 5.50% | 40 |
| Federal Funds Rate | > 5.50% | 20 |
| U.S. CPI inflation | value <= 2.00% | 90 |
| U.S. CPI inflation | > 2.00% and <= 3.00% | 80 |
| U.S. CPI inflation | > 3.00% and <= 4.00% | 65 |
| U.S. CPI inflation | > 4.00% and <= 5.00% | 45 |
| U.S. CPI inflation | > 5.00% | 25 |
| U.S. unemployment | value <= 3.50% | 85 |
| U.S. unemployment | > 3.50% and <= 4.50% | 75 |
| U.S. unemployment | > 4.50% and <= 5.50% | 55 |
| U.S. unemployment | > 5.50% and <= 6.50% | 35 |
| U.S. unemployment | > 6.50% | 20 |


**Important limitations:** these weights, bands and labels are illustrative and have not been calibrated or backtested. The subscore is not the full Arthvest macro regime model and does not include India conditions, market pricing, commodities or geopolitical events. Do not use it as a standalone trading signal.

## Source series

- Federal Funds Effective Rate: [FRED FEDFUNDS](https://fred.stlouisfed.org/series/FEDFUNDS)
- U.S. CPI: [FRED CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL)
- U.S. unemployment: [FRED UNRATE](https://fred.stlouisfed.org/series/UNRATE)
- India real GDP growth: [FRED INDGDPRQPSMEI](https://fred.stlouisfed.org/series/INDGDPRQPSMEI)
- India consumer price inflation (annual): [FRED FPCPITOTLZGIND](https://fred.stlouisfed.org/series/FPCPITOTLZGIND)
- India policy uncertainty: [FRED INDEPUINDXM](https://fred.stlouisfed.org/series/INDEPUINDXM)
- Indian rupees per U.S. dollar: [FRED DEXINUS](https://fred.stlouisfed.org/series/DEXINUS)
- India real effective exchange rate: [FRED CCRETT01INM661N](https://fred.stlouisfed.org/series/CCRETT01INM661N)

### Attribution and redistribution

FRED is the distribution endpoint used by this prototype; it is not always the original data producer. Follow the source-specific notes on each linked series page when citing or redistributing observations:

- OECD-sourced indicators (India GDP growth and India REER) should credit the OECD dataset as described on their FRED series pages. Review OECD copyright and reuse notes before redistributing those data.
- India annual consumer-price inflation should be attributed to the World Bank's World Development Indicators, retrieved via FRED.
- The India Economic Policy Uncertainty Index should credit Baker, Bloom and Davis as indicated on the series page.
- Federal Reserve Board and U.S. Bureau of Labor Statistics series retain source-attribution links in the API and dashboard.

Source labels in the UI are concise labels, not a substitute for reading the original series' citation and use terms.

Consult the linked series pages for current release cadence, attribution requirements and revisions.


## Cross-indicator comparison

`GET /api/macro/compare?indicators=fed-funds,us-inflation,us-unemployment&years=5` compares 2–5 supported keys over a 1, 3, 5, or 10 year calendar window. Each series is rebased to 100 on its own first archived display observation inside that window; `relative_change_percent` reports the movement from its baseline to its latest in-window reading. The series retain separate real observation dates and native units. No missing dates are interpolated, and positive baseline values are required for relative indexing. This is descriptive comparison, not correlation, causality, a forecast, or the calibrated full macro regime score. A reachable `DATABASE_URL` is required.
