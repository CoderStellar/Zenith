"""HTTP API for the Tool front end ("Try it out yourself"), and the static site itself.

  .venv/bin/uvicorn earthpull.api:app --port 8000      # then open http://localhost:8000

Endpoints (all GET, JSON):
  /api/variables                      catalog of variables the tool can analyse
  /api/analyze?w=&s=&e=&n=&var=&start=&end=
                                      monthly series, trend with 95% range and verdict, season and month trends,
                                      start-year sensitivity, and a per-grid-cell trend map when a global file exists
  /api/correlate?w=&s=&e=&n=&vars=a,b,c&start=&end=&lag=
                                      correlation engine for one region (earthpull.engine)
Every statistic comes from earthpull.trends / earthpull.engine, the same code the benchmarks test.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .core import DATA, BBox, _open_var, _standardize, load_catalog, pull
from .trends import SEASONS, _ols_ar1, season_trend, trend_report

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Earth Trend Detective API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])
GRACE_DIR = DATA / "raw" / "_global" / "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4"


def clean(x):
    """JSON-safe: NaN/inf -> None, numpy -> python."""
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else round(float(x), 6)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def verdict(r: dict) -> str:
    p = r.get("p_ar1", r.get("p"))
    if r.get("too_short") or p is None or not math.isfinite(p):
        return "Too short to tell"
    rising = r["slope_per_decade"] > 0
    agree = r["sen_ci_low"] > 0 if rising else r["sen_ci_high"] < 0
    if p < 0.05 and agree:
        return "Clear rise" if rising else "Clear fall"
    if p < 0.05:
        return "Likely change, but the two methods disagree"
    return "No clear trend yet"


def _box(w, s, e, n) -> BBox:
    try:
        return BBox.parse(f"{w},{s},{e},{n}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def has_map(vid: str) -> bool:
    return (DATA / "cubes" / f"{vid}.nc").exists() or (vid == "water_storage" and any(GRACE_DIR.glob("*.nc")))


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/variables")
def variables():
    cat = load_catalog()
    return [{"id": k, "name": v["name"], "instrument": v["instrument"], "units": v.get("units", ""),
             "product": f"{v['short_name']} {v.get('version') or ''}".strip(), "domain": v["domain"],
             "caveat": v.get("caveat", ""), "map": has_map(k),
             "fast": v["method"] == "giovanni" or (DATA / "cubes" / f"{k}.nc").exists() or k == "water_storage"}
            for k, v in cat.items() if not v.get("event_only")]


def _trend_map(vid: str, src: dict, box: BBox, start: str, end: str, max_cells: int = 6000) -> dict | None:
    import xarray as xr

    from .trendmap import ALPHA_FDR, trend_map

    cube = DATA / "cubes" / f"{vid}.nc"
    if cube.exists():
        da = xr.open_dataset(cube)[src["variable"]]
    elif vid == "water_storage":
        da = _open_var(sorted(GRACE_DIR.glob("*.nc"))[0], "lwe_thickness", "land_mask")
    else:
        return None
    da = _standardize(da).sel(lat=slice(box.south, box.north), lon=slice(box.west, box.east),
                              time=slice(start, end)).load()
    ny, nx = da.sizes["lat"], da.sizes["lon"]
    if ny * nx == 0:
        return None
    k = max(1, math.ceil(math.sqrt(ny * nx / max_cells)))  # keep the response small for big boxes
    if k > 1:
        da = da.coarsen(lat=k, lon=k, boundary="trim").mean()
    ds = trend_map(da, ALPHA_FDR.get(vid, 0.10))
    lat, lon = ds.lat.values, ds.lon.values
    dlat = float(abs(lat[1] - lat[0])) if len(lat) > 1 else 1.0
    dlon = float(abs(lon[1] - lon[0])) if len(lon) > 1 else 1.0
    return {"lat": lat.tolist(), "lon": lon.tolist(), "dlat": dlat, "dlon": dlon,
            "slope": ds.slope_per_decade.values.tolist(), "verdict": ds.verdict.values.astype(int).tolist(),
            "alpha_fdr": ds.attrs.get("alpha_fdr"), "coarsened_by": k}


@app.get("/api/analyze")
def analyze(w: float, s: float, e: float, n: float, var: str = Query(...), start: int = 2003, end: int = 2024,
            want_map: bool = True):
    cat = load_catalog()
    if var not in cat:
        raise HTTPException(404, f"unknown variable {var}")
    src = cat[var]
    box = _box(w, s, e, n)
    a, b = f"{start}-01-01", f"{end}-12-31"
    wide, rep = pull(box, a, b, [var])
    row = rep.iloc[0].to_dict() if len(rep) else {}
    if var not in wide or wide[var].notna().sum() < 24:
        raise HTTPException(422, f"no usable data: {row.get('status', 'nothing returned')}")
    ser = wide[var]
    breaks = tuple(src.get("breaks", ()))
    r = trend_report(ser, breaks)
    # monthly series on the regular calendar, anomalies, fitted line and its 95% band
    m = ser.copy()
    m.index = pd.PeriodIndex(m.index, freq="M")
    idx = pd.period_range(m.index.min(), m.index.max(), freq="M")
    m = m.reindex(idx)
    anom = m - m.groupby(m.index.month).transform("mean")
    ty = np.array([p.year + (p.month - 0.5) / 12 for p in idx])
    ok = np.isfinite(m.to_numpy(float))
    fit = _ols_ar1(ty, m.to_numpy(float), ok, breaks)
    tm = ty[ok].mean()
    from scipy import stats

    line = fit["slope"] * (ty - tm) + float(np.nanmean(anom.to_numpy(float)))
    band = stats.t.ppf(0.975, max(fit["n_eff"] - 6, 1)) * fit["se"] * np.abs(ty - tm)
    seasons = []
    for name, months in list(SEASONS.items()) + [(pd.Timestamp(2000, k, 1).strftime("%b"), (k,)) for k in range(1, 13)]:
        t = season_trend(ser, months)
        seasons.append({"period": name, "years": t["years"], "rate": t.get("slope_per_decade"),
                        "lo": t.get("ci_low"), "hi": t.get("ci_high"), "p": t.get("p"), "verdict": t["verdict"]})
    sens = []
    first, last = m.dropna().index.min(), m.dropna().index.max()
    for ys in range(first.year, last.year - 9):
        t = trend_report(m.loc[pd.Period(f"{ys}-01", "M"):], breaks)
        if not t.get("too_short"):
            sens.append({"start": ys, "rate": t["slope_per_decade"], "lo": t["ci_low"], "hi": t["ci_high"], "p": t["p_ar1"]})
    out = {
        "variable": {"id": var, "name": src["name"], "instrument": src["instrument"],
                     "units": row.get("units") or src.get("units", ""), "caveat": src.get("caveat", ""),
                     "product": f"{src['short_name']} {src.get('version') or ''}".strip(),
                     "known_changes": list(src.get("known_changes", ())) + list(breaks)},
        "region": {"w": box.west, "s": box.south, "e": box.east, "n": box.north, "via": row.get("via")},
        "series": {"months": [str(p) for p in idx], "values": m.to_numpy(float).tolist(),
                   "anomalies": anom.to_numpy(float).tolist(), "line": line.tolist(),
                   "lo": (line - band).tolist(), "hi": (line + band).tolist()},
        "trend": {k: r.get(k) for k in ("slope_per_decade", "ci_low", "ci_high", "p_ar1", "p_ttest", "sen_per_decade",
                                         "sen_ci_low", "sen_ci_high", "lag1_autocorr", "n_eff", "months", "first",
                                         "last", "years_needed", "pct_of_mean_per_decade", "pct_change_over_record")}
                 | {"verdict": verdict(r)},
        "seasons": seasons,
        "sensitivity": sens,
        "map": _trend_map(var, src, box, a, b) if want_map else None,
    }
    return clean(out)


@app.get("/api/correlate")
def correlate(w: float, s: float, e: float, n: float, vars: str, start: int = 2003, end: int = 2024, lag: int = 3):
    from . import engine

    cat = load_catalog()
    ids = [v for v in vars.split(",") if v in cat]
    if len(ids) < 2:
        raise HTTPException(400, "pick at least two variables")
    box = _box(w, s, e, n)
    wide, rep = pull(box, f"{start}-01-01", f"{end}-12-31", ids)
    names = {k: cat[k]["name"] for k in cat}
    res = engine.run(wide, names, max_lag=lag, n_surrogates=300,
                     breaks={k: tuple(cat[k]["breaks"]) for k in ids if cat[k].get("breaks")})
    pairs = res["pairs"]
    pt = res["partial_trends"]
    tr = pt[pt.p_alone < 0.05] if len(pt) else pt
    return clean({
        "variables": [{"id": v, "name": names[v]} for v in res["variables"]],
        "pairs": pairs[["a", "b", "best_lag", "r", "partial_r", "q", "surrogate_p", "granger_a_to_b_p",
                        "granger_b_to_a_p", "level", "verdict", "why"]].to_dict("records") if len(pairs) else [],
        "trend_checks": tr[["y", "x", "trend_alone_per_decade", "trend_with_x_per_decade", "x_effect_p",
                            "share_of_trend_x_accounts_for", "physics_rule", "verdict"]].to_dict("records") if len(tr) else [],
        "skipped": [v for v in ids if v not in res["variables"]],
    })


_NEWS_CACHE: dict = {}


@app.get("/api/news")
def news_feed(days: int = 7, limit: int = 40):
    """Latest environment headlines, each tied to the place it names (exact name match, no AI), with a box and the
    variables the topic table suggests. Cached for 30 minutes."""
    import time

    from . import news

    key = days
    hit = _NEWS_CACHE.get(key)
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    cat = load_catalog()
    tps = news.topics()
    df = news.latest_environment_news(days)
    rows = []
    for r in df.head(limit).itertuples():
        fast = {x["id"] for x in variables() if x["fast"]}  # only pre-tick variables that answer quickly
        vs = [v for v in tps[r.topic]["variables"] if v in cat and not cat[v].get("event_only") and v in fast]
        rows.append({"date": str(r.date), "title": r.title, "source": r.source, "link": r.link,
                     "topic": tps[r.topic]["label"], "place": r.place, "kind": r.kind,
                     "box": [round(float(x), 2) for x in (r.west, r.south, r.east, r.north)], "variables": vs})
    out = clean(rows)
    _NEWS_CACHE[key] = (time.time(), out)
    return out


@app.post("/api/explain")
def explain_endpoint(payload: dict):
    """Plain-language explanation of an /api/analyze or /api/correlate result (written by an AI model, numbers checked)."""
    from .explain import explain, links_facts, trend_facts

    kind = payload.get("kind")
    try:
        if kind == "trend":
            facts = trend_facts(payload["result"])
        elif kind == "links":
            facts = links_facts(payload["result"], payload["region"])
        else:
            raise HTTPException(400, "kind must be 'trend' or 'links'")
    except (KeyError, TypeError) as exc:
        raise HTTPException(400, f"bad result payload: {exc}")
    return clean(explain(kind, facts) | {"facts": facts})


# the static site (Tool/) at / so the page and the API share one address
app.mount("/", StaticFiles(directory=str(ROOT / "Tool"), html=True), name="tool")
