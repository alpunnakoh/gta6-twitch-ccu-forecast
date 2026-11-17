# Method — GTA VI launch-day Twitch CCU forecast (v3 / M25)

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

## The training family (v2 change #1)

v1.1 trained on the "already-unlocked" family, defined by a text rule on the
unlock description (not early-access, not simultaneous-global). That rule
has two holes, both fixed in v2:

1. **It lets in launches whose hour 1 is essentially empty.** Kingdom Come
   (414 viewers), HELLDIVERS 2 (419), Marathon (1,393), ARC Raiders (1,410)
   and Saros (6,400) all have "unverified" unlock text, so the text rule
   admits them — but their hour 1 is ~empty and their ratios explode
   100-1000x. Five such launches steepen every size slope (at hour 20,
   from -0.48 to -0.83) and blow up the residual spread. v2 requires
   **hour-1 viewers >= 10,000** for family membership.
2. **It locks out the two giants.** Elden Ring (875k) and Cyberpunk 2077
   (852k) have "single global" in their unlock text (a PC unlock), so the
   text rule rejects them — but their hour 1 IS a real launch hour (PC
   unlocked at or just before 00:00Z, consoles rolling midnight local) and
   their curves are family-shaped: dip to ~0.5, US-evening recovery to
   ~1.0. They are the only launches anywhere near GTA VI's scale, so
   excluding them left the family capped at 365k (The Last of Us Part II).
   v2 admits them by name.

Family (v2): already-unlocked AND v1 >= 10,000, PLUS Elden Ring and
Cyberpunk 2077 — 18 launches, v1 range 10,639..875,155. In the final case
the family also gains the four practice launches (RDR2, Ragnarök,
Spider-Man 2, Wolverine) — all rolling console launches with v1 >= 10k.

## The model (v2 changes #2 and #3)

For each hour h = 2..24, over the training family, fit in log space:

    ln(v_h / v_1) = a_h + b_h * (ln(v_1) - mean ln(v_1))

The log-ratio of hour h to hour 1, regressed on launch size. The slope is
shrunk toward 0 by n/(n+5) (v2: k=5; k=3 was best for the old family, k=5
wins on every GTA-VI-like subset for the new one).

**Extrapolation (v2 change #2).** GTA VI will very likely be bigger than
any training launch (family max 875k). v1.1 hard-clamped the target's
log-size to the training range. v2 uses **damped extrapolation**: beyond
the range, the effective log-size moves only half the way (factor 0.5)
past the boundary — neither clamped flat nor extrapolated at full slope.
Tested on the giant test (train capped at 365k, predict the two 850k+
giants): damped 0.122, clamped 0.133, unclamped 0.125, M23 0.181. The
progressive-cap test agrees (train capped at 365k, predict everything
above: damped 0.136, clamped 0.146, M23 0.212).

- Median: `p1 * exp(a_h + b_h * (effective ln p1 - mean))`
- Spread: the five quantiles are the **empirical quantiles of the fit's
  residuals** (5/25/50/75/95% of the sorted residuals, linear
  interpolation). The residuals are skewed and heavy-tailed, so a normal
  spread misprices the tails.

Fallbacks: an hour with fewer than 8 training launches uses the median
ratio of the launches that have it (sd 0.45); with no training launches at
all for an hour, the house baseline (persistence). If the family itself has
fewer than 8 launches, all comparables are used. If hour 1 has no print,
the last hourly history point with a positive viewers value is used (v1.1
fixed a crash on a `None` viewers value there; v2 keeps the fix and it is
covered by edge-case tests).

What the program deliberately does NOT use: the case's minute-by-minute
`history` and `streams`/`categories_hourly`. Hour 1's print already encodes
the launch's scale, and the shape comes from the comparables.

## The M25 change: size- and hour-dependent spread (v3)

One new signal survived every test in the M25 round (18 Nov, ~6h before
the deadline): **big launches have tighter relative spread than small
ones.** Thousands of channels average out, so the giants' hour-to-hour
ratios sit closer to the fitted curve than a 50k launch's do. Scaling the
log-spread around the median by a factor that falls with launch size cuts
the giants' LOO loss by ~22% (0.112 -> 0.087) and the giant test by ~16%.

The factor is a **threshold hinge**, not a plain linear term — a linear
size term also WIDENS the spread for mid-size launches and that widening
cost more than the narrowing gained (au&v1>=50k 0.199 vs 0.196):

    s(p1, h) = max((1 - 0.3 * max(0, ln p1 - ln 200k))
                   * (1 - 0.15 * (h - 13) / 12), 0.45)

- The hinge starts narrowing only above 200k hour-1 viewers, so launches
  below that keep M24's spread exactly.
- The hour term narrows the band slightly later in the day (the curve is
  most predictable once the US-evening peak has formed).
- The **floor of 0.45** is the safety device: for a 1.5-2M hour-1 print the
  unfloored factor would fall to 0.40/0.31, and the backtest shows a cliff
  there — a hinge slope of -0.4 (factor ~0.17 for the giants) made them
  WORSE than M24 (0.120 vs 0.112). The floor caps the extrapolation at the
  narrowest band the backtest can vouch for. At p1 = 875k the factor is
  0.63 (h2) .. 0.48 (h24); at p1 = 1.5M it is floored at 0.45 at every
  hour; below 200k it is 1.14 (h2) .. 0.86 (h24) from the hour term alone.
- The factor uses the RAW hour-1 print, not the damped effective size.

M25 wins on every decisive LOO subset vs M24 (table below) — the first
variant in three rounds to do so. Total LOO is 0.6687 vs M24's 0.6682
(flat; the total is dominated by the seven simultaneous launches and is
not the decision metric).

## Tested and rejected in v2 and v3 (M25 round)

- **Ensembles** (Vincentized log-quantile mean of M23/M24/F2-clamp/
  F2-noclamp/F4/F1 variants): mixed — best ensemble won rolling and
  v1>=100k but lost console, giants, giant test and cap365. Dropped.
- **Kernel-weighted local regression** on ln v1 (bandwidths 0.5-5.0):
  bw=2.5 won giants (0.104), giant test (0.115) and cap365 (0.129) but
  lost console (+0.0003) and au (+0.0002); combined with the spread hinge
  it still lost au. Dropped as the median model; its insight (local size
  weighting helps giants) is subsumed by the spread hinge.
- **Kernel-weighted spread** (weighted residual quantiles): won giants
  and total but lost rolling badly (0.245 vs 0.237). Dropped.
- **Uniform spread inflation** x1.05/x1.10/x1.15 on M24: worse on every
  decisive subset. M24's base spread is already right. Dropped.
- **Parametric polynomial median curves** (deg 2/3/4 over hours):
  worse on rolling/console/giants. Dropped.
- **Pre-launch features as a second regressor** (base24/base7d/pre14-day
  max/trend from the comparables' 14-day hourly history): correlations
  with M24 residuals are weak and sign-inconsistent across hours (base24
  +0.18..+0.28, base7d -0.43..+0.08, pre14max ~0, trend -0.11..+0.40);
  base24 is also not computable for the target (its pre-launch history
  is sparsely sampled). Dropped.
- **Weekday effects**: no signal — recovery ratios vary hugely within
  each weekday (Thu: -0.12..+2.31, Fri: -0.13..+2.37). Dropped.
- **Simultaneous-7 explosion predictors**: nothing in the case data
  (base24, base7d, pre-launch max, channels) predicts the 100-1000x
  explosions; and the final is a giant, not an empty hour-1. Left alone.
- **Channels (viewers per channel at hour 1) as a second regressor.**
  In-sample residual correlation reaches +0.49 at hour 15, but the
  leave-one-out test says it HURTS (rolling 0.263 vs 0.239 without it).
  Dropped.
- **Pre-launch 24h baseline as a signal.** Correlates +0.85 with ln(v1)
  (most of its information is already in hour 1), residual correlation
  only +0.2..+0.3, and it is NOT computable for the target (GTA VI's own
  pre-launch history is sparsely sampled, no 24h window). Dropped.
- **Leave-one-out residual spread** ("honest" spread) and **spread
  inflation x1.2 / x1.4**: both help the plain total (driven by the
  simultaneous targets) but HURT every GTA-VI-like subset. Dropped.
- **Median smoothing across hours**: no effect (rolling 0.2370 vs 0.2368).
  Dropped.
- **Dropping weak-tier launches** (Marvel Rivals): wins a hair on the
  rolling LOO subset but LOSES on the giant test (0.148 vs 0.133). Kept.
- **Slope shrink k=1/2/8/10**: k=5 is the sweet spot for the new family.

## Backtest (leave-one-out, 37 comparable launches, pinball loss on log scale)

| model | total | rolling | console-rolling | au & v1>=50k | giants | giant test | cap365k |
|---|---|---|---|---|---|---|---|
| house baseline (persistence) | 0.930 | 0.357 | 0.301 | — | — | — | — |
| v1.1 (M23: old family, k=3, clamp) | 0.464 | 0.264 | 0.238 | 0.230 | 0.181 | 0.181 | 0.212 |
| v2 (M24: new family, k=5, damp 0.5) | 0.668 | 0.237 | 0.167 | 0.196 | 0.112 | 0.122 | 0.136 |
| **v3 (M25: M24 + spread hinge)** | **0.669** | **0.232** | **0.164** | **0.196** | **0.087** | **0.102** | **0.121** |

**Read the total with care.** v2/v3's plain total (0.668) is worse than
v1.1's (0.464) — entirely because of seven simultaneous-global launches
whose hour 1 is ~empty (Silksong +2.03, HELLDIVERS 2 +1.79, Kingdom Come
+1.68, ARC Raiders +1.28, Battlefield 6 +1.12, Black Myth +0.97, Baldur's
Gate 3 +0.89 per-target loss vs v1.1). The new family cannot predict
their 100-1000x explosions, and no model that matters for GTA VI can:
GTA VI's hour 1 will be enormous, not empty. On every GTA-VI-like subset
v3 wins over v2 (rolling -2%, console -2%, v1>=100k -2%, giants -22%,
giant test -16%, cap365 -11%) and over v1.1 by much more. The final case
is a rolling-midnight console giant — the subsets, not the total, are the
decision metric.

Coverage of the 90% band on rolling launches: 0.86 (v2: 0.87, v1.1: 0.96,
over-wide); giants' coverage 0.96 (v2: 1.00) with typical median miss
~16% on giants (v2: 16%), ~48% on rolling (v2: 48%). End-to-end
validation through the shipped `main.py` reproduces the backtest total
exactly (0.6687, n=37). All 7 edge cases pass (missing/`None` hour-1
print, p1=0, no history, no comparables, p1=5M, p1=100, unusable
comparables). Runtime: 4 practice cases in ~0.2s (limit 8s/case).

Predicted GTA VI median shape (measured with v2 on the practice cases):
p1=300k dips to ~0.66x at hour 10 and peaks ~1.38x at hour 19; p1=875k
dips to ~0.50x and recovers to ~0.95x (peak IS hour 1, like Elden Ring);
p1=1.2M and 2M follow the same front-loaded pattern with the peak at
hours 2-3. The bigger the launch, the more front-loaded the day.

## Practice-board note (investigation, 18 Nov)

The practice leaderboard's top rows show loss ~1e-06 (typical miss 0%)
for 138 entries. The practice answers are NOT in the case files (verified:
the target launch is absent from the comparables; `history` holds only
pre-checkpoint points; `streams`/`categories_hourly` are null in
practice). The only way to score ~0 on practice is to hardcode the four
public historical curves (SullyGnome) keyed by game name — the rules
themselves say practice launches "anyone can look up" and "a practice
score is no guide to the final". Those entries gain nothing for the prize:
the final case (h00) is future data that cannot be hardcoded, and prizes
are decided on the final loss only. v2/v3 do NOT do this. Our honest
practice scores: v1.1 loss 0.201 (rank #2,679 of 6,250; median 0.21),
v2 loss 0.196 (rank #2,482 of 6,445). v3's practice score will be measured
after submission. Note the practice cases are small/medium launches
(23k-269k), so they barely test the giant-aware parts of v2/v3 — the
giant test and cap365k test are the better guides for the final.

## Risks

1. **GTA VI is bigger than any training launch.** Now mitigated, not
   solved: the family reaches 875k (the giants) and the size extrapolates
   damped (0.5) past it, and the spread floor (0.45) stops the band from
   over-narrowing at 1.5M+. If hour 1 prints ~2M, the shape is a damped
   extension of the giants' front-loaded pattern — the best evidence
   available, but still an extension.
2. **The final's hour-1 print is a mean of minute reads**, while training
   ratios come from SullyGnome hourly averages. The two measures are close
   but not identical; a systematic gap would shift every ratio slightly.
3. **Single-day idiosyncrasy**: a streamer event, an outage, or a
   record-breaking moment (e.g. a 1M+ raid) can move individual hours far
   outside any historical band. The wide 90% band is the defence.
4. **The house AI forecast** (superbot, max reasoning, made 2026-11-18
   23:00Z on the same case data) is the prize bar together with the house
   baseline. Our edge is a fitted, LOO-validated statistical model; the
   house model's edge is frontier-model judgement. The final decides.

## Sources

- Case data: SullyGnome.com hourly Twitch category averages (via the kit).
- Scale context (not used by the model): Coilr's launch-day estimate
  (~5.8M concurrent players at peak, 3.9-8.6M range, players-per-viewer
  0.69-1.85 from the biggest Western launches); Foresee market ~68% that
  the Twitch category peaks above 1.3M viewers; GTA V category ~81.6k
  viewers at the kit's probe time (2026-11-17).
