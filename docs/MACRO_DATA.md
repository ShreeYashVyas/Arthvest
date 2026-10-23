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

## Configured indicators

| Key | Series | Unit | Frequency | Freshness threshold |
|---|---|---|---|---:|
| `fed-funds` | FEDFUNDS | Percent | Monthly | 120 days |
| `us-inflation` | CPIAUCSL | Percent year over year (calculated) | Monthly | 100 days |
| `us-unemployment` | UNRATE | Percent, seasonally adjusted | Monthly | 100 days |
| `india-policy-uncertainty` | INDEPUINDXM | Index | Monthly | 120 days |
| `usd-inr` | DEXINUS | INR per USD | Daily, excluding non-publishing days | 7 days |
| `india-reer` | CCRETT01INM661N | Index (2015=100) | Monthly | 100 days |

Series metadata and links are returned dynamically by `/api/macro/catalog`.

## Calculation rules

- U.S. CPI inflation is calculated as the 12-month percentage change in `CPIAUCSL`, using the same observation month in the prior year.
- The U.S. unemployment rate, effective federal funds rate, India policy-uncertainty index, INR/USD exchange rate and Indian REER are displayed from the latest non-missing observation.
- Historical CPI inflation points are calculated for each month where a matching observation from 12 months earlier is available.
- Missing, invalid and non-finite observations are not silently converted to zero.
- Freshness is measured from the source observation date, not the retrieval time. Thresholds are provisional operational checks, not statements about economic significance.
- FRED observations may be revised. Arthvest caches each fetched series in-process for 15 minutes; this is not a persistent database.

## Provisional U.S. subscore

The score currently combines only three U.S. observations:

| Component | Weight |
|---|---:|
| Federal Funds Effective Rate | 25% |
| U.S. CPI inflation | 45% |
| U.S. unemployment rate | 30% |

Fixed threshold bands translate each input into a 0–100 component score and calculate a weighted average. The score is withheld if a required observation is unavailable, invalid or stale.

**Important limitations:** these weights, bands and labels are illustrative and have not been calibrated or backtested. The subscore is not the full Arthvest macro regime model and does not include India conditions, market pricing, commodities or geopolitical events. Do not use it as a standalone trading signal.

## Source series

- Federal Funds Effective Rate: [FRED FEDFUNDS](https://fred.stlouisfed.org/series/FEDFUNDS)
- U.S. CPI: [FRED CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL)
- U.S. unemployment: [FRED UNRATE](https://fred.stlouisfed.org/series/UNRATE)
- India policy uncertainty: [FRED INDEPUINDXM](https://fred.stlouisfed.org/series/INDEPUINDXM)
- Indian rupees per U.S. dollar: [FRED DEXINUS](https://fred.stlouisfed.org/series/DEXINUS)
- India real effective exchange rate: [FRED CCRETT01INM661N](https://fred.stlouisfed.org/series/CCRETT01INM661N)

Consult the linked series pages for current release cadence, attribution requirements and revisions.
