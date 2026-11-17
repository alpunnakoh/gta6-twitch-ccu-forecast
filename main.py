"""GTA VI launch-day Twitch CCU forecaster (gta6-twitch-ccu-forecast-01).

Reads one case (makefun/twitch-ccu-case/v1) from the input directory and
writes, for each of hours 2..24 of the release day, five quantiles
(5/25/50/75/95%) of that hour's Twitch concurrent viewers in the
"Grand Theft Auto VI" category.

Method (M25; see METHOD.md for the full write-up and backtest numbers)
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

i.e. the log-ratio of hour h to hour 1, regressed on launch size. The slope
is shrunk toward 0 by n/(n+5). GTA VI will very likely be bigger than any
training launch (family max 875k), so the target's log-size is NOT hard
clamped to the training range: beyond the range it moves only half the way
(damped extrapolation, factor 0.5). A damped step beats both a hard clamp
and a full extrapolation on the giant test (train capped at 365k, predict
the two 850k+ giants: 0.122 vs 0.133 clamped, 0.125 unclamped; M23: 0.181).

The median forecast is p1 * exp(a_h + b_h * (effective ln p1 - mean)), and
the five quantiles are the EMPIRICAL quantiles of the fit's residuals
(5/25/50/75/95% of the sorted residuals, linear interpolation): the
residuals are skewed and heavy-tailed, so a normal spread misprices the
tails. Spread inflation and leave-one-out residuals were both tested and
both HURT the GTA-VI-like subsets, so the plain in-sample empirical spread
stays as the base.

M25 change -- size- and hour-dependent spread (the one new signal that
survived every test in the M25 round). Big launches have TIGHTER relative
spread than small ones (thousands of channels average out): scaling the
log-spread by a factor that falls with launch size cuts the giants' LOO
loss by ~22%. The factor is a threshold hinge -- it only starts narrowing
above 200k hour-1 viewers, so mid-size launches keep M24's spread
unchanged (a plain linear size term hurt them) -- times a mild hour
narrowing (the curve is most predictable late in the day), with a FLOOR
of 0.45 so that even a 2-5M hour-1 print can never narrow the band past
the point the backtest can vouch for (an over-narrowed band was the one
way this idea failed: hinge slope -0.4 made the giants WORSE than M24):

    s(p1, h) = max((1 - 0.3 * max(0, ln p1 - ln 200k))
                   * (1 - 0.15 * (h - 13) / 12), 0.45)

and each hour's log-quantiles are scaled around their median by s.
At p1 = 875k the factor is 0.63 (h2) .. 0.48 (h24); at p1 = 1.5M it is
floored at 0.45; below 200k it is 1.14 (h2) .. 0.86 (h24) from the hour
term alone. Ideas tested and REJECTED in the M25 round: ensembles of
M23/M24/F2/F4 variants (mixed, worse on giants), kernel-weighted local
regression (better giants, worse console/au), uniform spread inflation
(worse everywhere), parametric polynomial median curves (worse), channels
and pre-launch baseline as regressors (weak/inconsistent correlations,
uncomputable for the target), weekday effects (none: huge within-weekday
spread). The 138 near-zero-loss practice-board entries are hardcoded
public historical curves and cannot work on the final fresh case.

Backtest (leave-one-out over the 37 comparable launches in the kit,
pinball loss on the log scale, lower is better). NOTE: the plain total
(0.669) is WORSE than M23's (0.464) -- entirely because of seven
simultaneous-global launches whose hour 1 is ~empty (Silksong, HELLDIVERS
2, Kingdom Come, ARC Raiders, Battlefield 6, Black Myth, Baldur's Gate 3);
the new family cannot predict their 100-1000x explosions, and neither can
any model that matters for GTA VI, whose hour 1 will be enormous. On
every GTA-VI-like subset M25 beats M24 (and M23):
    rolling-midnight launches only   0.232 (M24 0.237, M23 0.264)
    console-only rolling launches   0.164 (M24 0.167, M23 0.238)
    already-unlocked & v1 >= 50k    0.196 (M24 0.196, M23 0.230)
    v1 >= 100k                      0.222 (M24 0.226, M23 0.244)
    the two giants (Elden Ring, Cyberpunk)  0.087 (M24 0.112, M23 0.181)
    giant test (train capped at 365k, predict the giants) 0.102 (M24 0.122)
    progressive-cap test (train <= 365k, all launches above) 0.121 (M24 0.136)
Coverage of the 90% band on rolling launches: 0.86 (M24 0.87, M23 0.96);
giants' coverage 0.96 (M24 1.00) with typical median miss ~16% (M24 16%).
End-to-end validation through the shipped main.py reproduces the backtest
total exactly (0.6687, n=37).

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
SHRINK_K = 5          # slope shrinkage n / (n + SHRINK_K)
DAMP = 0.5            # extrapolation beyond the training size range: move
                      # only this fraction of the way past the boundary
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


def fit_hour(pairs, log_p1):
    """Fit ln(v_h / v_1) ~ a + b * (ln(v_1) - mean ln(v_1)) over `pairs`
    [(ln v1, ln(v_h / v1))]. Returns (median_log_ratio, sorted_residuals):
    the residuals of the shrunk-slope fit, sorted, so the caller can take
    empirical quantiles instead of assuming a normal spread."""
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    mx = mean(xs)
    my = mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = 0.0
    if sxx > 0:
        slope = sum((x - mx) * (y - my) for x, y in pairs) / sxx
    slope *= len(pairs) / (len(pairs) + SHRINK_K)
    median_log = my + slope * (log_p1 - mx)
    resid = sorted(y - (my + slope * (x - mx)) for x, y in pairs)
    return median_log, resid


def effective_log_size(log_p1, lo, hi):
    """Damped extrapolation: inside the training range the size is used as
    is; outside it, move only DAMP of the way past the boundary. A
    record-size launch is therefore neither clamped flat to the biggest
    training launch nor extrapolated at full slope -- both of which scored
    worse on the giant test (train capped at 365k, predict the 850k+
    giants)."""
    if log_p1 > hi:
        return hi + DAMP * (log_p1 - hi)
    if log_p1 < lo:
        return lo + DAMP * (log_p1 - lo)
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

    rows = []
    for row in case["forecast"]:
        h = int(row["hour"])
        pairs = []
        for _, curve in train:
            if h in curve:
                pairs.append((math.log(curve[1]), math.log(curve[h] / curve[1])))
        if len(pairs) >= MIN_HOUR_N:
            med_log, resid = fit_hour(pairs, log_p1)
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
        log_qs = [med + s * (q - med) for q in log_qs]
        quantiles = []
        prev = 0.0
        for log_q in log_qs:
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
