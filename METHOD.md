# Method — GTA VI launch-day Twitch CCU forecast

## What the program does

`main.py` reads one case (`makefun/twitch-ccu-case/v1`) and writes, for hours
2..24 of the release day (UTC), five quantiles (5/25/50/75/95%) of Twitch
concurrent viewers in the "Grand Theft Auto VI" category. The forecast is
anchored on the case's hour-1 print and on the shapes of past big launches'
release days, carried in the case as `comparables` (SullyGnome hourly Twitch
category averages).

## The one fact that drives the model

A launch day's shape depends on **when the game unlocks relative to the UTC
day**:

- **Rolling midnight-local unlock** (Red Dead Redemption 2, God of War
  Ragnarök, Zelda: Tears of the Kingdom, Ghost of Yōtei): hour 1 already has
  New Zealand, Australia, Asia, central Europe and the UK playing. The curve
  dips overnight, jumps at the US unlocks (05:00Z east coast, 08:00Z west
  coast) and peaks in the US-evening / Europe-evening overlap, hours ~19-22,
  at roughly 1.3-3.6x hour 1.
- **One simultaneous global unlock later in the day** (Black Myth: Wukong
  02:00Z, Hollow Knight: Silksong 14:00Z, Battlefield 6 ~14:00Z): hour 1 is
  nearly empty (a few hundred viewers) and the curve explodes 100-1000x
  later. Averaging these in destroys the forecast for a rolling launch.
- **Early-access launches** (Hogwarts Legacy, Diablo IV, Starfield): the
  audience already peaked days before hour 1, so their curves are flat.

So the model trains **only on the "already-unlocked" family**: comparables
that are not early-access-contaminated and not simultaneous-global. GTA VI
is a rolling midnight-local console launch with no early access, so this is
its family. (In the final case the family also gains the four practice
launches — RDR2, Ragnarök, Spider-Man 2, Wolverine — all rolling console
launches.)

## The model

For each hour h = 2..24, over the training family, fit in log space:

    ln(v_h / v_1) = a_h + b_h * (ln(v_1) - mean ln(v_1))

The log-ratio of hour h to hour 1, regressed on launch size. The slope is
shrunk toward 0 by n/(n+3). The target's log-size is clamped to the
training range, so a record-size launch never extrapolates past the data.

- Median: `p1 * exp(a_h + b_h * (clamped ln p1 - mean))`
- Spread: the five quantiles are the **empirical quantiles of the fit's
  residuals** (5/25/50/75/95% of the sorted residuals, linear
  interpolation). The residuals are skewed and heavy-tailed, so a normal
  spread misprices the tails — v1.1 replaced the normal spread (residual
  sd floored at 0.12) with empirical quantiles, and the shrink constant
  with it (k=5 → k=3). Backtest: total 0.471 → **0.464**, rolling launches
  0.270 → **0.264**, console-rolling 0.255 → **0.238** (see table below).
  The near-tied alternative (k=2 + empirical, total 0.458) was NOT
  adopted: it wins on total but loses on the rolling subset, and GTA VI
  is a rolling launch.

Fallbacks: an hour with fewer than 8 training launches uses the median
ratio of the launches that have it (sd 0.45); with no training launches at
all for an hour, the house baseline (persistence). If the family itself has
fewer than 8 launches, all comparables are used. If hour 1 has no print,
the last hourly history point with a positive viewers value is used (v1
crashed on a `None` viewers value there — fixed in v1.1).

What the program deliberately does NOT use: the case's minute-by-minute
`history` and `streams`/`categories_hourly`. Hour 1's print already encodes
the launch's scale, and the shape comes from the comparables; the minute
history adds no signal for the shape once hour 1 is known. (Checked in
backtest: adding channels-per-viewer features did not help — not shipped.)

## Backtest (leave-one-out, 37 comparable launches, pinball loss on log scale)

| model | mean loss | rolling launches | console-rolling |
|---|---|---|---|
| house baseline (persistence) | 0.930 | 0.357 | 0.301 |
| median ratio + normal spread (all) | 0.795 | — | — |
| size-adjusted, all launches | 0.461 | 0.284 | 0.268 |
| v1.0 (size-adj, already-unlocked family, k=5, normal spread) | 0.471 | 0.270 | 0.255 |
| **v1.1 (this model: k=3, empirical residual quantiles)** | **0.464** | **0.264** | **0.238** |

Coverage of the 90% band: 0.80 (v1.0: 0.85 — the empirical spread is
narrower in the tails, which the pinball loss rewards when the median is
well placed). Typical median miss: ~129% (v1.0: ~133%) — the
launch-day curve is genuinely hard to pin down hour by hour, and the loss
rewards an honest spread rather than a narrow guess.

Predicted GTA VI median shape (hour-1 print 300k-1M, measured with v1.1
on the practice cases): dip to ~0.76x at hour 4 and ~0.5x at hours 10-12,
rise to a peak of ~0.8-1.0x at hours 20-22, ~0.6-0.8x at hour 24. The
shape flattens with size because of the clamp — a deliberate guard against
extrapolating the size slope past the data.

## Risks

1. **GTA VI is bigger than any training launch.** If hour 1 prints above
   ~850k viewers, the model clamps to the largest training launch and the
   shape is a guess informed by the rolling family, not a measurement.
2. **The final's hour-1 print is a mean of minute reads**, while training
   ratios come from SullyGnome hourly averages. The two measures are close
   but not identical; a systematic gap would shift every ratio slightly.
3. **Single-day idiosyncrasy**: a streamer event, an outage, or a
   record-breaking moment (e.g. a 1M+ raid) can move individual hours far
   outside any historical band. The wide 90% band is the defence.

## Sources

- Case data: SullyGnome.com hourly Twitch category averages (via the kit).
- Scale context (not used by the model): Coilr's launch-day estimate
  (~5.8M concurrent players at peak, 3.9-8.6M range, players-per-viewer
  0.69-1.85 from the biggest Western launches); Foresee market ~68% that
  the Twitch category peaks above 1.3M viewers; GTA V category ~81.6k
  viewers at the kit's probe time (2026-11-17).
