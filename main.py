"""GTA VI launch-day Twitch CCU forecaster (gta6-twitch-ccu-forecast-01).

Reads one case (makefun/twitch-ccu-case/v1) from the input directory and
writes, for each of hours 2..24 of the release day, five quantiles
(5/25/50/75/95%) of that hour's Twitch concurrent viewers in the
"Grand Theft Auto VI" category.

Method (see METHOD.md for the full write-up and backtest numbers)
------------------------------------------------------------------
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
forecast, so the model trains ONLY on the "already-unlocked" family:
comparables that are not early-access-contaminated and not
simultaneous-global.

For each hour h = 2..24, over the training family, fit in log space

    ln(v_h / v_1) = a_h + b_h * (ln(v_1) - mean ln(v_1))

i.e. the log-ratio of hour h to hour 1, regressed on launch size. The slope
is shrunk toward 0 by n/(n+5). The target's log-size is clamped to the
training range so a record-size launch never extrapolates past the data.
The median forecast is p1 * exp(a_h + b_h * (clamped ln p1 - mean)), and
the spread is the within-family residual standard deviation (floored at
0.12 log units), giving q_tau = p1 * exp(median + z_tau * sd) with the
standard-normal quantiles (-1.645, -0.674, 0, 0.674, 1.645).

Backtest (leave-one-out over the 37 comparable launches in the kit,
pinball loss on the log scale, lower is better):
    house baseline (persistence)      0.930
    this model                        0.471
    this model, rolling launches only 0.270 (baseline 0.357 there)
Coverage of the 90% band in backtest: 0.85; typical median miss ~133%
(the launch-day curve is genuinely hard to pin down hour by hour).

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
MIN_GROUP = 8         # need at least this many training launches, else fall back
MIN_HOUR_N = 8        # need at least this many launches with hour h, else fallback
SD_FLOOR = 0.12       # minimum log-spread per hour
SD_FALLBACK = 0.45    # spread when an hour has too little data
BASE_SIGMA = 0.15     # house baseline spread, used only as a last resort


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


def pstdev(values):
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def fit_hour(pairs, log_p1):
    """Fit ln(v_h / v_1) ~ a + b * (ln(v_1) - mean ln(v_1)) over `pairs`
    [(ln v1, ln(v_h / v1))]. Returns (median_log_ratio, sd)."""
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
    resid = [y - (my + slope * (x - mx)) for x, y in pairs]
    sd = max(SD_FLOOR, pstdev(resid)) if len(resid) >= 2 else SD_FALLBACK
    return median_log, sd


def forecast_case(case, name):
    if case.get("levels") != LEVELS:
        raise ValueError(f"{name} asks for levels {case.get('levels')}, not {LEVELS}")
    known = case.get("known") or []
    first = next((k for k in known if k.get("hour") == 1), None)
    if first is None:
        # No hour-1 print: fall back to the last hourly history point, else 1.
        hourly = case.get("history_hourly") or []
        p1 = float(hourly[-1]["viewers"]) if hourly else 1.0
    else:
        p1 = float(first.get("viewers") or 0)
    p1 = max(1.0, p1)

    # Training launches: comparables with a usable release-day curve.
    launches = []
    for comp in sorted(case.get("comparables") or [], key=lambda c: c.get("name", "")):
        curve = extract_curve(comp)
        if 1 in curve and len(curve) >= 12:
            launches.append((comp, curve))
    family = [(c, v) for c, v in launches if already_unlocked(c)]
    train = family if len(family) >= MIN_GROUP else launches

    log_sizes = [math.log(v[1]) for _, v in train] if train else []
    lo = min(log_sizes) if log_sizes else 0.0
    hi = max(log_sizes) if log_sizes else 0.0
    log_p1 = min(max(math.log(p1), lo), hi) if log_sizes else math.log(p1)

    rows = []
    for row in case["forecast"]:
        h = int(row["hour"])
        pairs = []
        for _, curve in train:
            if h in curve:
                pairs.append((math.log(curve[1]), math.log(curve[h] / curve[1])))
        if len(pairs) >= MIN_HOUR_N:
            med_log, sd = fit_hour(pairs, log_p1)
        elif pairs:
            med_log = median([y for _, y in pairs])
            sd = SD_FALLBACK
        else:
            # No training data for this hour: house baseline (persistence).
            med_log, sd = 0.0, BASE_SIGMA * math.sqrt(h - 1)
        quantiles = []
        prev = 0.0
        for z in Z:
            q = p1 * math.exp(med_log + z * sd)
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
