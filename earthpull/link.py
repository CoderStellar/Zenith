"""Does something in place A go with a change in place B? Plain statistics, no AI.

For source (box A, variable X) and target (box B, variable Y):
1. Anomalies: remove the seasonal cycle from both series.
2. Lagged correlation for lags -L..+L (positive lag = A leads B), with an effective sample size corrected
   for autocorrelation (Bretherton et al. 1999), Benjamini-Hochberg across lags.
3. Composite: when X at A is in its top 10%, how different is Y at B (at the best lag)? Mann-Whitney test.
4. Transport check: monthly 850 hPa wind (about 1.5 km up) over A, projected on the direction from A to B.

Wording comes from fixed rules. A shared cause (one weather pattern touching both places) can also make
two places move together; the tool says so every time.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import xarray as xr
from scipy import stats

from .core import DATA, BBox, _clip_dates, _fetch_giovanni, _raw_dir, load_catalog, login, pull

FREQ_LABEL = {"monthly": "months", "daily": "days"}


def get_series(bbox: BBox, vid: str, start: str, end: str, freq: str, progress=None) -> tuple[pd.Series, str, str]:
    cat = load_catalog()
    if freq == "daily":
        twin = cat[vid].get("event_twin", vid)
        src = cat[twin]
        if not (src["cadence"] == "daily" and src["method"] == "giovanni"):
            raise ValueError(f"{cat[vid]['name']} has no daily version here; use monthly")
        login()
        s0, s1 = _clip_dates(src, start, end)
        df, units = _fetch_giovanni(src, bbox, s0, s1, _raw_dir(twin, bbox, s0, s1), monthly=False)
        s = df["value"].resample("D").mean()
        return s, units or src.get("units", ""), f"{src['name']} ({src['instrument']})"
    wide, rep = pull(bbox, start, end, [vid], progress=progress)
    if vid not in wide:
        raise ValueError(str(rep.iloc[0].get("status")))
    s = wide[vid]
    s.index = s.index.to_timestamp()
    units = (rep.get("units", pd.Series([""])).iloc[0]) or cat[vid].get("units", "")
    return s, units, f"{cat[vid]['name']} ({cat[vid]['instrument']})"


def anomalies(s: pd.Series, freq: str) -> pd.Series:
    if freq == "monthly":
        return s - s.groupby(s.index.month).transform("mean")
    doy = s.index.dayofyear
    clim = s.groupby(doy).mean()
    clim = pd.concat([clim.iloc[-15:], clim, clim.iloc[:15]]).rolling(31, center=True, min_periods=10).mean().iloc[15:-15]
    return s - clim.reindex(doy).values


def _lag1(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    return float(np.corrcoef(x[:-1], x[1:])[0, 1]) if len(x) > 3 else 0.0


def lag_table(a: pd.Series, b: pd.Series, max_lag: int) -> pd.DataFrame:
    from statsmodels.stats.multitest import multipletests

    idx = a.index.union(b.index)
    a, b = a.reindex(idx), b.reindex(idx)
    ra, rb = _lag1(a.values), _lag1(b.values)
    rows = []
    for lag in range(-max_lag, max_lag + 1):
        x, y = a.values, b.shift(-lag).values  # positive lag: B later than A
        ok = np.isfinite(x) & np.isfinite(y)
        n = int(ok.sum())
        if n < 20:
            continue
        r = float(np.corrcoef(x[ok], y[ok])[0, 1])
        n_eff = max(3.0, n * (1 - ra * rb) / (1 + ra * rb))
        t = r * math.sqrt((n_eff - 2) / max(1e-12, 1 - r * r))
        p = float(2 * stats.t.sf(abs(t), n_eff - 2))
        rows.append({"lag": lag, "r": r, "n": n, "n_eff": n_eff, "p": p})
    df = pd.DataFrame(rows)
    if len(df):
        df["q"] = multipletests(df.p, method="fdr_bh")[1]
    return df


def wind_toward(src_box: BBox, dst_box: BBox, months: pd.DatetimeIndex | None = None) -> dict | None:
    """Fraction of months when 850 hPa wind over A blows toward B (needs the wind cubes)."""
    cu, cv = DATA / "cubes" / "wind_u850.nc", DATA / "cubes" / "wind_v850.nc"
    if not (cu.exists() and cv.exists()):
        return None
    from .core import _box_mean

    u = _box_mean(xr.open_dataset(cu)["U850"].load(), src_box)["value"]
    v = _box_mean(xr.open_dataset(cv)["V850"].load(), src_box)["value"]
    ca = ((src_box.south + src_box.north) / 2, (src_box.west + src_box.east) / 2)
    cb = ((dst_box.south + dst_box.north) / 2, (dst_box.west + dst_box.east) / 2)
    la1, lo1, la2, lo2 = map(math.radians, (*ca, *cb))
    bearing = math.atan2(math.sin(lo2 - lo1) * math.cos(la2),
                         math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1))
    along = u * math.sin(bearing) + v * math.cos(bearing)  # m/s toward B
    km = 6371 * math.acos(min(1, math.sin(la1) * math.sin(la2) + math.cos(la1) * math.cos(la2) * math.cos(lo2 - lo1)))
    out = {"bearing_deg": (math.degrees(bearing) + 360) % 360, "distance_km": km,
           "share_toward": float((along > 0).mean()), "mean_toward_ms": float(along.mean())}
    if months is not None and len(months):
        sel = along[along.index.to_period("M").isin(pd.PeriodIndex(months, freq="M"))]
        if len(sel):
            out["share_toward_events"] = float((sel > 0).mean())
            out["n_event_months"] = int(len(sel))
    return out


def link(src_box: BBox, src_var: str, dst_box: BBox, dst_var: str, start: str, end: str,
         freq: str = "monthly", max_lag: int | None = None, progress=None) -> dict:
    max_lag = max_lag if max_lag is not None else (3 if freq == "monthly" else 10)
    a, ua, na = get_series(src_box, src_var, start, end, freq, progress)
    b, ub, nb = get_series(dst_box, dst_var, start, end, freq, progress)
    aa, ab = anomalies(a, freq), anomalies(b, freq)
    tab = lag_table(aa, ab, max_lag)
    out = {"source": na, "target": nb, "units_a": ua, "units_b": ub, "a": a, "b": b, "aa": aa, "ab": ab,
           "lags": tab, "freq": freq}
    if tab.empty:
        out["verdict"] = "Not enough overlapping data"
        return out
    sig = tab[tab.q < 0.05]
    best = (sig if len(sig) else tab).loc[lambda d: d.r.abs().idxmax()]
    out["best"] = best.to_dict()
    lead = sig[sig.lag > 0].r.abs().max() if len(sig[sig.lag > 0]) else 0
    lagb = sig[sig.lag < 0].r.abs().max() if len(sig[sig.lag < 0]) else 0
    unit = FREQ_LABEL[freq]
    if not len(sig):
        out["verdict"] = "No clear link: the two places do not move together more than chance would give"
    else:
        sign = "higher" if best.r > 0 else "lower"
        when = "at the same time" if best.lag == 0 else (
            f"{int(best.lag)} {unit} later" if best.lag > 0 else f"{int(-best.lag)} {unit} earlier")
        strength = "strong" if abs(best.r) >= 0.5 else "moderate" if abs(best.r) >= 0.3 else "weak"
        out["verdict"] = (f"Linked ({strength}, r = {best.r:.2f}): when A is unusually high, B tends to be {sign} {when}")
        if best.lag > 0 and lagb >= lead * 0.9:
            out["verdict"] += ". But B also leads A about as strongly, so the direction is unclear"
    # composite at the best lag
    lag = int(best.lag)
    idx = aa.index.union(ab.index)
    x, y = aa.reindex(idx), ab.reindex(idx).shift(-lag)
    ok = x.notna() & y.notna()
    thr = x[ok].quantile(0.9)
    hi, rest = y[ok & (x >= thr)], y[ok & (x < thr)]
    if len(hi) >= 5 and len(rest) >= 5:
        out["composite"] = {"threshold": float(thr), "n_events": int(len(hi)), "b_during_events": float(hi.mean()),
                            "b_otherwise": float(rest.mean()),
                            "p_mannwhitney": float(stats.mannwhitneyu(hi, rest, alternative="two-sided").pvalue),
                            "event_times": list(hi.index)}
    out["wind"] = wind_toward(src_box, dst_box, pd.DatetimeIndex(out.get("composite", {}).get("event_times", [])))
    out["caveat"] = ("Moving together is not proof that A causes B. One large weather pattern can affect both "
                     "places. The wind check shows whether air could carry something from A to B.")
    return out
