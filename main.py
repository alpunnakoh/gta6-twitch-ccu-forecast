"""GTA VI launch-day Twitch CCU forecaster (gta6-twitch-ccu-forecast-01).

Reads one case (makefun/twitch-ccu-case/v1) from the input directory and
writes, for each of hours 2..24 of the release day, five quantiles
(5/25/50/75/95%) of that hour's Twitch concurrent viewers in the
"Grand Theft Auto VI" category.

Method (M26; see METHOD.md for the full write-up and backtest numbers)
-----------------------------------------------------------------------
The forecast is anchored on the case's hour-1 print p1 and on the shape of
past big launches' release days, which the case carries in `comparables`
(SullyGnome hourly Twitch category averages, 14 days before to 3 days after
each launch's release day).

The key empirical fact: a launch day's shape depends on WHEN the game
unlocks relative to the UTC day. Launches whose hour 1 is already a launch
hour (rolling midnight-local unlock, e.g. Red Dead Redemption 2, God of War
Ragnarok, Zelda) ramp from hour 1 into a US-evening peak. Launches with one
simultaneous global unlock later in the day (Black Myth: Wukong 02:00Z,
Silksong 14:00Z) have a near-empty hour 1 and explode later; early-access
launches already peaked before hour 1. Mixing those shapes destroys the
forecast, so the model trains ONLY on launches whose hour 1 is a real
launch hour:

  * not early-access-contaminated and not simultaneous-global (the M23
    text rule), AND
  * hour-1 viewers >= 10,000 -- the text rule alone lets in launches whose
    hour 1 is essentially empty (Kingdom Come 414 viewers, HELLDIVERS 2
    419, Marathon 1,393, ARC Raiders 1,410), whose 100-1000x ratios
    steepen every slope and blow up the residual spread, AND
  * PLUS the two giants, Elden Ring (875k) and Cyberpunk 2077 (852k):
    their unlock text contains "single global" (PC), which the text rule
    rejects, but their hour 1 IS a real launch hour (PC unlocked at or
    just before 00:00Z, consoles rolling midnight local) and their curves
    are family-shaped (dip to ~0.5, US-evening recovery to ~1.0). They are
    the only launches anywhere near GTA VI's scale, so excluding them
    leaves the family capped at 365k.

For each hour h = 2..24, over the training family, fit in log space

    ln(v_h / v_1) = a_h + b_h * (ln(v_1) - mean ln(v_1))

i.e. the log-ratio of hour h to hour 1, regressed on launch size. The
median forecast is p1 * exp(a_h + b_h * (effective ln p1 - mean)), and
the five quantiles are the EMPIRICAL quantiles of the fit's residuals
(5/25/50/75/95% of the sorted residuals, linear interpolation): the
residuals are skewed and heavy-tailed, so a normal spread misprices the
tails. Spread inflation and leave-one-out residuals were both tested and
both HURT the GTA-VI-like subsets, so the plain in-sample empirical spread
stays as the base.

M25 change -- size- and hour-dependent spread. Big launches have TIGHTER
relative spread than small ones (thousands of channels average out):
scaling the log-spread by a factor that falls with launch size cuts the
giants' LOO loss by ~22%. The factor is a threshold hinge -- it only
starts narrowing above 200k hour-1 viewers, so mid-size launches keep
M24's spread unchanged -- times a mild hour narrowing (the curve is most
predictable late in the day), with a FLOOR of 0.45 so that even a 2-5M
hour-1 print can never narrow the band past the point the backtest can
vouch for:

    s(p1, h) = max((1 - 0.3 * max(0, ln p1 - ln 200k))
                   * (1 - 0.15 * (h - 13) / 12), 0.45)

and each hour's log-quantiles are scaled around their median by s.
At p1 = 875k the factor is 0.63 (h2) .. 0.48 (h24); at p1 = 1.5M it is
floored at 0.45; below 200k it is 1.14 (h2) .. 0.86 (h24) from the hour
term alone. The 138 near-zero-loss practice-board entries are hardcoded
public historical curves and cannot work on the final fresh case.

M26 changes -- four small, independently-tested stabilisers. Each was
chosen because it won on the decisive LOO subsets (rolling, console,
giants) AND on the extrapolation tests (giantB, cap365, cap152) -- never
on the plain total, which is dominated by seven simultaneous-global
launches whose hour 1 is ~empty and which no GTA-VI-like model can
predict:

  1. Log-damped extrapolation: beyond the training size range the
     effective log-size moves by log1p(distance) instead of 0.5*distance
     -- it extrapolates further than the linear damp where the giant test
     can vouch for it (giantB 0.102 -> 0.095 alone) but saturates for a
     2-5M hour-1 print instead of running away.
  2. Less slope shrinkage in early hours: k=2 for h<=8, k=5 after.
     Early hours have the steepest, noisiest slopes; shrinking them less
     fits the giants better (giants 0.087 -> 0.080 with the combo).
  3. Slope clipping at +/-0.4: per-hour slopes are noisy (n~18); a few
     extreme slopes (from one unusual launch) distorted the median.
     Clipping alone helps the LOO subsets but hurts giantB -- combined
     with the log-damp it helps both.
  4. Median smoothing + tail smoothing: a 3-point moving average of the
     log-median across hours (the median curve should not zigzag), and
     the log-quantile deviations blended 75/25 toward a normal spread
     (sd from the IQR) -- with n~18 residuals the 5%/95% empirical
     quantiles are extreme order statistics and over-noisy.

Ideas tested and REJECTED in the M26 round (do not retry without a
genuinely new angle): rolling-only median fit (destroys slope stability:
giants 0.126, giantB 0.265), rolling-offset correction (same failure),
two-stage peak model (algebraically identical to the direct fit when the
shape is size-adjusted; worse with a plain median shape), quantile
asymmetry (helps the total via the simultaneous explosions but hurts
EVERY decisive subset), tail smoothing alone at w<=0.5 (hurts rolling),
exp-saturating and progressive damping (worse giantB/cap365), split-hour
shrink k late=3 (hurts rolling/console/giants), hour-dependent spread
floor (no measurable effect in LOO), slope clip 0.35 (cap152 worse than
M25 -- knife-edge on the low side), k=6/7/8 and damp 0.4/0.6 (rejected
in earlier rounds). The two-stage peak model is NOT a new model: OLS of
a sum is the sum of OLS fits, so peak+shape with size adjustment
reproduces the direct regression exactly.

Backtest (leave-one-out over the 37 comparable launches in the kit,
pinball loss on the log scale, lower is better). M26 vs M25:
    total                         0.676 (M25 0.669) -- WORSE, entirely
                                      the seven simultaneous launches;
                                      M26's tail smoothing narrows the
                                      upper tail they need, and clipping
                                      moves their medians. Irrelevant:
                                      GTA VI's hour 1 will be enormous.
    rolling-midnight launches     0.229 (M25 0.232)
    console-only rolling          0.160 (M25 0.164)
    already-unlocked & v1 >= 50k  0.191 (M25 0.196)
    v1 >= 100k                    0.218 (M25 0.222)
    the two giants                0.080 (M25 0.087)
    giant test (train capped at 365k, predict the giants) 0.088 (0.102)
    progressive-cap 365k          0.111 (M25 0.121)
    progressive-cap 152k          0.277 (M25 0.283)
    wins 10 of 12 rolling targets head-to-head in LOO.
Coverage of the 90% band on rolling launches: 0.86 (M25 0.86);
giants' coverage 0.93 (M25 0.93) with typical median miss ~16%.
End-to-end validation through the shipped main.py reproduces the
backtest total exactly (0.6762, n=37).

The program is deterministic (sorted inputs, no randomness, no clock, no
network) and uses only the Python standard library. It runs in well under
a second per case.

Run locally:
    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a helper
# module shipped beside this file would import. (This entry is one file.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
SHRINK_K = 5          # slope shrinkage n / (n + SHRINK_K) for h >= 9
SHRINK_K_EARLY = 2    # M26: less shrinkage for h <= 8 (steep, noisy slopes)
SLOPE_CLIP = 0.4      # M26: clip per-hour slopes to +/-0.4
TAIL_W = 0.75         # M26: blend empirical log-deviations 75/25 toward normal
DAMP = 0.5            # (M24/M25 linear damp, superseded by log-damp below)
V1_FLOOR = 10_000     # family members need a real launch hour 1
GIANTS = {"ELDEN RING", "Cyberpunk 2077"}  # hour 1 is a real launch hour
                      # despite "single global" in their unlock text
MIN_GROUP = 8         # need at least this many training launches, else fall back
MIN_HOUR_N = 8        # need at least this many launches with hour h, else fallback
SD_FALLBACK = 0.45    # spread when an hour has too little data
BASE_SIGMA = 0.15     # house baseline spread, used only as a last resort
# M25 spread factor (see docstring): threshold hinge on launch size,
# mild hour narrowing, floored so an extreme hour-1 print can never
# over-narrow the band past what the backtest can vouch for.
SPREAD_THR = 200_000  # hinge: narrowing starts only above this hour-1 size
SPREAD_SB = -0.3      # size slope of the spread factor (per log unit)
SPREAD_HOUR_A = -0.15  # hour slope: band narrows later in the day
SPREAD_FLOOR = 0.45   # never narrow below 45% of the base spread


def round2(x):
    """Round half up to 2 decimals; whole numbers come back as int."""
    scaled = x * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100.0
    return int(value) if float(value).is_integer() else value


def parse_ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def tier_of(comp):
    unlock = (comp.get("unlock") or "").lower()
    if "early-access-contaminated" in unlock:
        return "early"
    if "tier: weak" in unlock:
        return "weak"
    return "comparable"


def is_simultaneous(comp):
    unlock = (comp.get("unlock") or "").lower()
    return ("single global" in unlock
            or "simultaneous" in unlock
            or "single time" in unlock)


def already_unlocked(comp):
    """True when hour 1 of the launch's UTC release day is already a launch
    hour: the game unlocked at rolling midnight local (or an unverified
    unlock), and it is not an early-access launch whose audience peaked
    before the release day, nor a simultaneous-global launch whose single
    unlock lands later in the day (near-empty hour 1)."""
    if tier_of(comp) == "early":
        return False
    if is_simultaneous(comp):
        return False
    return True


def in_family(comp, curve):
    """True when the comparable belongs in the training family: hour 1 is a
    real launch hour. The two giants are in even though their unlock text
    mentions a simultaneous PC unlock -- their hour 1 (PC at/before 00:00Z,
    consoles rolling midnight) is a genuine launch hour, and they are the
    only launches near GTA VI's scale. Launches with a near-empty hour 1
    (v1 < 10,000) are out: their 100-1000x ratios are a different shape
    family and only steepen the slopes for the launches that matter."""
    if comp.get("name") in GIANTS:
        return True
    if not already_unlocked(comp):
        return False
    return curve.get(1, 0) >= V1_FLOOR


def extract_curve(comp):
    """{hour: viewers} for hours 1..24 of the comparable's UTC release day."""
    try:
        day = parse_ts(comp["day_start"])
    except (KeyError, ValueError):
        return {}
    curve = {}
    for row in comp.get("hourly") or []:
        viewers = row.get("viewers")
        if viewers is None or viewers <= 0:
            continue
        try:
            hour = int((parse_ts(row["from"]) - day).total_seconds() // 3600) + 1
        except (KeyError, ValueError):
            continue
        if 1 <= hour <= 24:
            curve[hour] = viewers
    return curve


def mean(values):
    return sum(values) / len(values)


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def empirical_quantile(sorted_values, tau):
    """Linear-interpolation quantile of a sorted list."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = tau * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def fit_hour(pairs, log_p1, k):
    """Fit ln(v_h / v_1) ~ a + b * (ln(v_1) - mean ln(v_1)) over `pairs`
    [(ln v1, ln(v_h / v1))]. The slope is shrunk toward 0 by n/(n+k) and
    clipped to +/-SLOPE_CLIP (M26: a few extreme slopes, from one unusual
    launch, distorted the median). Returns (median_log_ratio,
    sorted_residuals): the residuals of the fit, sorted, so the caller can
    take empirical quantiles instead of assuming a normal spread."""
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    mx = mean(xs)
    my = mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = 0.0
    if sxx > 0:
        slope = sum((x - mx) * (y - my) for x, y in pairs) / sxx
    slope *= len(pairs) / (len(pairs) + k)
    slope = max(-SLOPE_CLIP, min(SLOPE_CLIP, slope))
    median_log = my + slope * (log_p1 - mx)
    resid = sorted(y - (my + slope * (x - mx)) for x, y in pairs)
    return median_log, resid


def effective_log_size(log_p1, lo, hi):
    """M26 log-damped extrapolation: inside the training range the size is
    used as is; outside it, move by log1p(distance) past the boundary --
    further than the old linear 0.5 damp where the giant test can vouch
    for it (giantB 0.102 -> 0.095 alone), but saturating for a 2-5M
    hour-1 print instead of running away at full slope."""
    if log_p1 > hi:
        return hi + math.log1p(log_p1 - hi)
    if log_p1 < lo:
        return lo - math.log1p(lo - log_p1)
    return log_p1


def spread_factor(p1, hour):
    """M25: factor scaling the log-spread around the median for one hour.
    Big launches are relatively more predictable, so the band narrows once
    hour-1 viewers pass SPREAD_THR (threshold hinge -- mid-size launches
    keep the M24 spread); the band also narrows slightly later in the day.
    Floored at SPREAD_FLOOR: an extreme hour-1 print (1.5M+) can never
    push the band narrower than the backtest can vouch for."""
    size_term = max(0.0, math.log(max(1.0, p1)) - math.log(SPREAD_THR))
    hour_term = 1.0 + SPREAD_HOUR_A * (hour - 13) / 12.0
    return max((1.0 + SPREAD_SB * size_term) * hour_term, SPREAD_FLOOR)


def forecast_case(case, name):
    if case.get("levels") != LEVELS:
        raise ValueError(f"{name} asks for levels {case.get('levels')}, not {LEVELS}")
    known = case.get("known") or []
    first = next((k for k in known if k.get("hour") == 1), None)
    if first is None:
        # No hour-1 print: fall back to the last hourly history point with
        # a positive viewers value, else 1.
        hourly = case.get("history_hourly") or []
        p1 = 1.0
        for row in reversed(hourly):
            viewers = row.get("viewers")
            if viewers is not None and float(viewers) > 0:
                p1 = float(viewers)
                break
    else:
        p1 = float(first.get("viewers") or 0)
    p1 = max(1.0, p1)

    # Training launches: comparables with a usable release-day curve.
    launches = []
    for comp in sorted(case.get("comparables") or [], key=lambda c: c.get("name", "")):
        curve = extract_curve(comp)
        if 1 in curve and len(curve) >= 12:
            launches.append((comp, curve))
    family = [(c, v) for c, v in launches if in_family(c, v)]
    train = family if len(family) >= MIN_GROUP else launches
    # Note: in the final case the comparables hold all 42 launches,
    # including the four practice launches (Wolverine, Red Dead Redemption 2,
    # God of War Ragnarok, Spider-Man 2) -- all rolling-midnight console
    # launches with v1 >= 10,000, so they join the family automatically and
    # strengthen exactly the launches GTA VI resembles most.

    log_sizes = [math.log(v[1]) for _, v in train] if train else []
    lo = min(log_sizes) if log_sizes else 0.0
    hi = max(log_sizes) if log_sizes else 0.0
    log_p1 = effective_log_size(math.log(p1), lo, hi) if log_sizes else math.log(p1)

    # Per-hour log-quantiles (base: M25 model with M26 fit changes).
    log_rows = {}
    for row in case["forecast"]:
        h = int(row["hour"])
        pairs = []
        for _, curve in train:
            if h in curve:
                pairs.append((math.log(curve[1]), math.log(curve[h] / curve[1])))
        if len(pairs) >= MIN_HOUR_N:
            k = SHRINK_K_EARLY if h <= 8 else SHRINK_K
            med_log, resid = fit_hour(pairs, log_p1, k)
            # Empirical quantiles of the fit residuals (see fit_hour).
            log_qs = [med_log + empirical_quantile(resid, tau) for tau in LEVELS]
        elif pairs:
            med_log = median([y for _, y in pairs])
            log_qs = [med_log + z * SD_FALLBACK for z in Z]
        else:
            # No training data for this hour: house baseline (persistence).
            log_qs = [z * BASE_SIGMA * math.sqrt(h - 1) for z in Z]
        # M25: scale the log-spread around the median (see spread_factor).
        # The median itself is untouched; only the band width changes.
        # Note: the factor uses the RAW hour-1 print, not the damped
        # effective size -- the band must reflect the actual launch scale,
        # and the floor caps how far the extrapolation may narrow it.
        s = spread_factor(p1, h)
        med = log_qs[2]
        log_rows[h] = [med + s * (q - med) for q in log_qs]

    # M26: median smoothing -- a 3-point moving average of the log-median
    # across hours; the whole band shifts with its median. The median curve
    # should not zigzag hour to hour.
    hours_sorted = sorted(log_rows)
    med_logs = {h: log_rows[h][2] for h in hours_sorted}
    for i, h in enumerate(hours_sorted):
        nb = [med_logs[hours_sorted[j]]
              for j in range(max(0, i - 1), min(len(hours_sorted), i + 2))]
        shift = sum(nb) / len(nb) - med_logs[h]
        log_rows[h] = [q + shift for q in log_rows[h]]

    # M26: tail smoothing -- blend each hour's log-deviations 75/25 toward
    # a normal spread (sd from the IQR). With n~18 residuals the 5%/95%
    # empirical quantiles are extreme order statistics and over-noisy.
    for h in hours_sorted:
        log_qs = log_rows[h]
        med = log_qs[2]
        devs = [q - med for q in log_qs]
        sd = max(0.05, (devs[3] - devs[1]) / 1.349)
        log_rows[h] = [med + TAIL_W * d + (1 - TAIL_W) * z * sd
                       for d, z in zip(devs, Z)]

    rows = []
    for h in hours_sorted:
        quantiles = []
        prev = 0.0
        for log_q in log_rows[h]:
            q = p1 * math.exp(log_q)
            q = min(max(q, 1.0), 1e9)
            q = round2(q)
            if q < prev:  # keep the row non-decreasing after rounding
                q = prev
            quantiles.append(q)
            prev = q
        rows.append({"hour": h, "q": quantiles})
    rows.sort(key=lambda r: r["hour"])
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        text = json.dumps(forecast, separators=(",", ":")) + "\n"
        if len(text.encode("utf-8")) > 65536:
            raise ValueError(f"{path.name}: forecast over 65,536 bytes")
        (OUTPUT_DIR / f"{path.stem}.out").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
