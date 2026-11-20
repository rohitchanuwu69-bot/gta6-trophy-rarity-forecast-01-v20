# Trophy Dilution Forecaster v20

[![make.fun](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/rohitchanuwu69-bot/gta6-trophy-rarity-forecast-01-v20/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/rohitchanuwu69-bot/gta6-trophy-rarity-forecast-01-v20/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01)

Entry for the [make.fun bounty "Forecast how many GTA VI players earn each trophy in week one"](https://make.fun/bounty/gta6-trophy-rarity-forecast-01) ($250, entries close 2026-11-21T11:30:00Z).

## What it does

`main.py` reads one case from `$MAKEFUN_INPUT_DIR` (or `/input`) and writes
one forecast per trophy to `$MAKEFUN_OUTPUT_DIR` (or `/output`): five
quantiles (5%, 25%, 50%, 75%, 95%) of each trophy's earn rate at the case's
target, as the page prints it, to two decimals. Python 3.13 standard library
only, deterministic, no network, well under 8 seconds per case.

## How it forecasts

Two regimes, picked from the case's own history:

- **Flat** — the page has not moved since launch night. The median is a
  whole-player count: the last read's earned count, plus 2 players for the
  first 29 trophies in list order, plus a 20% newcomer-earn bump for the
  trophies whose rates are the top three distinct sub-100 values, divided by
  the target player count (last players times the documented first-refresh
  factor 3868/638). The spread is a tiny 0.0075 logit total. The four fast
  trophies carry an asymmetric hedge band instead: q05 at a 10% newcomer
  fraction, q95 at 30%, inner quantiles at the printed median.
- **Moving** — the page has moved. The median comes from log-time
  least-squares fits of players and earned counts, but only on the segment
  after the last big jump (largest single-read players jump over 1.5x, else
  a rate jump over 0.5 logit), so a refresh jump or a plateau is not
  extrapolated as continued growth. If the segment's last three reads are
  flat (logit range under 0.01), the median is their level instead. The
  spread floor is 0.03 logit total, growing with horizon and fit residuals,
  capped near 1.1. A trophy at 100% stays 100%.

## Local validation (site pinball scale, aggregates only)

- Flat checks: fine-corrected truth 0.0007 / coverage 1.0; earned counts
  frozen 0.2057 / 0.4545; old fitted truth 0.1658 / 0.5273.
- Moving scenarios: steady growth 0.0066 / 1.0; flat-then-refresh jump
  0.0017 / 1.0; fast growth then plateau 0.0053 / 1.0.
- Practice inputs p00/p01: 55 rows each, ids 1-55 once each, quantiles
  non-decreasing, two runs byte-identical, about 0.05 s per case.

## License

MIT. See LICENSE.
