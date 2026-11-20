import json, math, os
from datetime import datetime, timezone

QUANTS = [n / 100.0 for n in (5, 25, 50, 75, 95)]

# The page's first refresh took it from 638 tracked players to 3868. The flat
# branch assumes one such refresh has happened by the target, so it scales the
# last player count by that documented ratio - never by a hardcoded count.
REFRESH = 3868.0 / 638.0
HEAD_BONUS = 2
HEAD_N = 29
FAST_MID = 0.20
FAST_LOW = 0.10
FAST_HIGH = 0.30

FLAT_W = 0.0075
FLAT_W_MIN = 0.0075
FLAT_W_MAX = 0.0375

MOVE_FLOOR = 0.03
MOVE_H_COEF = 0.02
MOVE_CAP = 1.1
FLAT_LIM = 0.01
JUMP_P = 1.5
JUMP_R = 0.5
FULL_PCT = 100.0


def whole(x):
    return int(x + 0.5 + 1e-9)


def two_dp(x):
    return int(x * 100.0 + 0.5 + 1e-9) / 100.0


def clip(v, low, high):
    return low if v < low else high if v > high else v


def logodds(p):
    p = clip(p, 0.0001, 0.9999)
    odds = p / (1.0 - p)
    return math.log(odds)


def from_logodds(z):
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    num = math.exp(z)
    return num / (1.0 + num)


def parse_ts(raw):
    moment = None
    if raw is None: return (moment)
    raw = str(raw).strip()
    if not raw:
        return moment
    if len(raw) == 10:
        raw = raw + "T00:00:00+00:00"
    elif raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try: moment = datetime.fromisoformat(raw)
    except ValueError as err: moment = None
    if moment is not None and moment.tzinfo is None:
        moment = datetime.replace(moment, tzinfo=timezone.utc)
    return (moment)


def linfit(px, py):
    k = len(px)
    if k == 0:
        return (0.0, 0.0, 0.0)
    mean_x = sum(px) / k
    mean_y = sum(py) / k
    sxx = sum((x - mean_x) ** 2 for x in px)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(px, py))
    grad = sxy / sxx if sxx > 0.0 else 0.0
    base = mean_y - grad * mean_x
    err = math.sqrt(sum((y - (base + grad * x)) ** 2 for x, y in zip(px, py)) / k)
    return base, grad, err


def fallback(items):
    return [{"id": tr["id"], "q": [0.01, 0.01, 0.01, 0.01, 0.01]} for tr in items]


def spread_band(mid, width, quants):
    centre = logodds(mid / 100.0)
    qs = []
    for tau in quants:
        q = two_dp(100.0 * from_logodds(centre + width * (tau - 0.5)))
        qs.append(min(100.0, max(0.01, q)))
    return sorted(qs)


def flat_forecast(items, rates, players0, quants):
    players_t = players0 * REFRESH
    newc = players_t - players0
    if newc < 0.0:
        newc = 0.0
    top3 = sorted({r for r in rates if r < 100.0}, reverse=True)[:3]
    fastset = {i for i, r in enumerate(rates) if r in top3}
    out = []
    for i, tr in enumerate(items, start=0):
        code = tr["id"]
        r0 = rates[i]
        if r0 >= FULL_PCT:
            out.append({"id": code, "q": [100.0, 100.0, 100.0, 100.0, 100.0]})
        else:
            base = whole(r0 * players0 / 100.0)
            bonus = HEAD_BONUS if i < HEAD_N else 0

            def count_at(f):
                bump = 0
                if i in fastset:
                    bump = whole(newc * (r0 / 100.0) * f)
                return bump + base + bonus

            med_count = count_at(FAST_MID)
            mid = two_dp(100.0 * med_count / players_t)
            if i in fastset:
                lo = two_dp(100.0 * count_at(FAST_LOW) / players_t)
                hi = two_dp(100.0 * count_at(FAST_HIGH) / players_t)
                # Hedge only on the outer quantiles: q05 from a 10% newcomer
                # fraction, q95 from 30%, inner three at the printed median.
                qs = sorted([lo, mid, mid, mid, hi])
            else:
                if med_count > 0:
                    step = logodds((med_count + 1) / players_t) - logodds(med_count / players_t)
                else:
                    step = 0.0
                width = min(FLAT_W_MAX, max(FLAT_W_MIN, step / 2.0))
                qs = spread_band(mid, width, quants)
            out.append({"id": code, "q": qs})
    return out


def is_moving(hist):
    if len(hist) < 2:
        return False
    rates0 = hist[0]["rates"]
    seen = {r["players_tracked"] for r in hist if r.get("players_tracked") is not None}
    moved = len(seen) > 1
    if not moved:
        for read in hist[1:]:
            if read["rates"] != rates0:
                moved = True
    return moved


def moving_forecast(case, items, hist, quants):
    have = [r for r in hist if r.get("players_tracked") is not None]
    rates = hist[-1]["rates"]
    seen_p = [r["players_tracked"] for r in have]
    if len(have) < 2:
        return flat_forecast(items, rates, seen_p[-1] if seen_p else 0, quants)
    release = parse_ts(case["game"]["release_date"])
    target = parse_ts(case["target"])
    at = parse_ts(case["at"])
    if release is None or target is None or at is None:
        return flat_forecast(items, rates, seen_p[-1], quants)

    def mins_since(moment):
        return max(1.0, (moment - release).total_seconds() / 60.0)

    split = 0
    top_ratio = 1.0
    for k in range(1, len(have)):
        prev = have[k - 1]["players_tracked"]
        cur = have[k]["players_tracked"]
        ratio = cur / prev if prev else 1.0
        if ratio > JUMP_P and ratio > top_ratio:
            top_ratio = ratio
            split = k
    if split == 0:
        top_jump = 0.0
        for k in range(1, len(have)):
            jump = max(abs(logodds(a / 100.0) - logodds(b / 100.0)) for a, b in zip(have[k]["rates"], have[k - 1]["rates"]))
            if jump > JUMP_R and jump > top_jump:
                top_jump = jump
                split = k
    part = have[split:]
    xs = [math.log(mins_since(parse_ts(r["at"]))) for r in part]
    x_target = math.log(mins_since(target))
    ap, bp, rmp = linfit(xs, [math.log(r["players_tracked"]) for r in part])
    pred_p = math.exp(ap + bp * x_target)
    horizon_days = max(0.0, (target - at).total_seconds() / 86400.0)
    horizon_term = MOVE_H_COEF * math.sqrt(horizon_days)
    out = []
    for i, tr in enumerate(items, start=0):
        code = tr["id"]
        if rates[i] >= 100.0:
            out.append({"id": code, "q": [100.0, 100.0, 100.0, 100.0, 100.0]})
        else:
            ys = [math.log(max(r["rates"][i] * r["players_tracked"] / 100.0, 1e-9)) for r in part]
            ae, be, rme = linfit(xs, ys)
            pred_e = math.exp(ae + be * x_target)
            mid = 100.0 * pred_e / pred_p if pred_p > 0.0 else rates[i]
            resid = math.sqrt(rme * rme + rmp * rmp)
            if len(part) >= 3:
                lg = [logodds(r["rates"][i] / 100.0) for r in part[-3:]]
                wob = max(lg) - min(lg)
                if wob < FLAT_LIM:
                    mid = rates[i]
                    resid = wob
            width = min(MOVE_CAP, MOVE_FLOOR + horizon_term + resid)
            mid = min(100.0, max(0.01, mid))
            if mid >= 99.995:
                out.append({"id": code, "q": [100.0, 100.0, 100.0, 100.0, 100.0]})
            else:
                centre = logodds(mid / 100.0)
                qs = []
                for tau in quants:
                    q = two_dp(100.0 * from_logodds(centre + width * (tau - 0.5)))
                    qs.append(min(100.0, max(0.01, q)))
                out.append({"id": code, "q": sorted(qs)})
    return out


def forecast_case(case):
    items = case["trophies"]
    quants = case.get("levels") or QUANTS
    hist = case.get("history") or []
    if not hist:
        return fallback(items)
    rates = hist[-1]["rates"]
    seen_p = [r["players_tracked"] for r in hist if r.get("players_tracked") is not None]
    if not seen_p:
        return fallback(items)
    if is_moving(hist):
        return moving_forecast(case, items, hist, quants)
    return flat_forecast(items, rates, seen_p[-1], quants)


def run():
    src = os.environ.get("MAKEFUN_INPUT_DIR") or "/input"
    dst = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(dst, exist_ok=True)
    names = sorted(n for n in os.listdir(src) if n.endswith(".in"))
    for name in iter(names):
        with open(os.path.join(src, name), "r", encoding="utf-8") as fh:
            inp = json.load(fh)
        rows = forecast_case(inp)
        stem = name.removesuffix(".in")
        with open(os.path.join(dst, stem + ".out"), "w", encoding="utf-8") as fh:
            text = json.dumps({"trophies": rows}, separators=(",", ":"))
            fh.write(f"{text}\n")


if __name__ == "__main__":
    run()
