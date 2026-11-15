"""Build Tool/data.js (the Pacific-states demo front end) from real NASA data via the earthpull engine.

  python scripts/build_tool_data.py fetch      # download everything (states in parallel; cached afterwards)
  python scripts/build_tool_data.py build      # compute statistics and write Tool/data.js

Regions: US Census 2024 state outlines (Alaska clipped at 180 degrees: the far-western Aleutians are dropped).
Every number comes from earthpull.trends (memory-adjusted trend, Theil-Sen agreement, verdict).
"""
import json
import sys
import warnings
from datetime import date
from multiprocessing import Pool

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box as sbox

sys.path.insert(0, ".")
from earthpull.core import DATA, load_catalog, pull  # noqa: E402
from earthpull.trends import (LEAKAGE_MARGIN_KM, buffer_km, percent_change, region_area_km2,  # noqa: E402
                              season_series, season_trend, trend_report)

warnings.filterwarnings("ignore")
STATES = {"Alaska": "AK", "California": "CA", "Hawaii": "HI", "Oregon": "OR", "Washington": "WA"}
PERIODS = {"air_temp": ("1980-01-01", "2024-12-31"), "precip": ("2001-01-01", "2024-12-31"),
           "aod_modis_aqua": ("2002-07-01", "2024-12-31"), "water_storage": ("2003-01-01", "2024-12-31"),
           "soil_moisture": ("2003-01-01", "2024-12-31")}


def outlines() -> dict:
    g = gpd.read_file("zip://" + str(DATA / "boundaries" / "cb_2024_us_state_500k.zip")).to_crs(4326)
    out = {}
    for name in STATES:
        geom = g[g.NAME == name].union_all()
        if name == "Alaska":  # drop the Aleutian islands west of 180 so the region does not wrap the globe
            geom = geom.intersection(sbox(-180, 50, -129, 72))
        out[name] = geom
    return out


def _fetch_state(name):
    shape = outlines()[name]
    res = {}
    for vid, (a, b) in PERIODS.items():
        w, rep = pull(None, a, b, [vid], shape=shape)
        res[vid] = rep.iloc[0].to_dict()
    return name, res


def fetch():
    with Pool(len(STATES)) as p:
        for name, res in p.imap_unordered(_fetch_state, STATES):
            print(name, {k: (v.get("status"), v.get("via"), v.get("months")) for k, v in res.items()}, flush=True)


def verdict(r: dict) -> str:
    if r.get("too_short") or "p" not in r and "p_ar1" not in r:
        return "Too short to tell"
    p = r.get("p_ar1", r.get("p"))
    rising = r["slope_per_decade"] > 0
    agree = r["sen_ci_low"] > 0 if rising else r["sen_ci_high"] < 0
    if p < 0.05 and agree:
        return "Clear rise" if rising else "Clear fall"
    if p < 0.05:
        return "Likely change, methods disagree"
    return "No clear trend yet"


def build():
    cat = load_catalog()
    shapes = outlines()
    data = {name: {} for name in STATES}
    series = {}
    for name, shape in shapes.items():
        for vid, (a, b) in PERIODS.items():
            w, rep = pull(None, a, b, [vid], shape=shape)
            series[(name, vid)] = w[vid] if vid in w else pd.Series(dtype=float)
    out_vars = {}

    def stat(r, scale=1.0):
        return {k: (None if r.get(k) is None or (isinstance(r.get(k), float) and np.isnan(r[k])) else round(float(r[k]) * scale, 4))
                for k in ("slope_per_decade", "ci_low", "ci_high", "sen_per_decade", "sen_ci_low", "sen_ci_high")} | {
            "p": round(float(r.get("p_ar1", r.get("p", np.nan))), 6), "verdict": verdict(r)}

    # air temperature (K -> C is the same for rates); yearly anomalies vs 1991-2020
    temp_years = list(range(1980, 2025))
    temp_series = {}
    for name in STATES:
        s = series[(name, "air_temp")]
        r = trend_report(s)
        data[name]["temp"] = stat(r) | {"months": r["months"], "n_eff": round(r["n_eff"]), "record": "1980-2024"}
        s2 = s.copy()
        s2.index = pd.PeriodIndex(s2.index, freq="M")
        ann = s2.groupby(s2.index.year).mean()
        anom = ann - ann.loc[1991:2020].mean()
        temp_series[name] = [round(float(anom.get(y, np.nan)), 3) if y in anom.index else None for y in temp_years]
        data[name]["temp"]["mean"] = round(float(s.mean()) - 273.15, 2)
    # precipitation: mm/hr -> mm/month climatology; trend as % of mean per decade
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    seasonal = {}
    for name in STATES:
        s = series[(name, "precip")]
        r = trend_report(s)
        mean = float(s.mean())
        st = stat(r)
        data[name]["precip"] = st | {
            "pct_per_decade": round(100 * r["slope_per_decade"] / mean, 2), "pct_ci_low": round(100 * r["ci_low"] / mean, 2),
            "pct_ci_high": round(100 * r["ci_high"] / mean, 2), "mean_mm_per_year": round(mean * 24 * 365.25, 0),
            "months": r["months"], "n_eff": round(r["n_eff"]), "record": "2001-2024"}
        s2 = s.copy()
        s2.index = pd.PeriodIndex(s2.index, freq="M")
        clim = s2.groupby(s2.index.month).mean()
        seasonal[name] = [round(float(clim[m] * 24 * pd.Period(f"2001-{m:02d}").days_in_month), 1) for m in range(1, 13)]
    # summer smoke/haze (MODIS Aqua AOD, June-August)
    for name in STATES:
        s = series[(name, "aod_modis_aqua")]
        t = season_trend(s, (6, 7, 8))
        st = stat(t) if "slope_per_decade" in t else {"verdict": t["verdict"]}
        st |= {"years": t["years"], "record": "summers 2003-2024",
               "pct_per_decade": round(float(t.get("pct_of_mean_per_decade", np.nan)), 1) if t.get("mean") else None,
               "mean": round(float(t.get("mean", np.nan)), 3) if t.get("mean") else None}
        if t.get("series") is not None:
            st["by_year"] = {int(k): round(float(v), 3) for k, v in t["series"].items()}
        data[name]["smoke"] = st
    # GRACE total water storage: cm/decade == mm/yr; volume inside the outline and with the leakage margin
    for name, shape in shapes.items():
        s = series[(name, "water_storage")]
        if s.notna().sum() < 120:  # Hawaii: the islands are ocean at GRACE's resolution
            data[name]["water"] = {"slope_per_decade": None, "ci_low": None, "ci_high": None, "verdict": "No GRACE data (too small for GRACE)",
                                   "km3_per_year": None, "km3_per_year_with_margin": None, "reliable": False,
                                   "area_km2": round(region_area_km2(shape)), "record": "n/a"}
            continue
        r = trend_report(s)
        inside = r["slope_per_decade"] * region_area_km2(shape) * 1e-6
        try:
            big = buffer_km(shape, LEAKAGE_MARGIN_KM)
            wb, _ = pull(None, *PERIODS["water_storage"], ["water_storage"], shape=big)
            margin = trend_report(wb["water_storage"])["slope_per_decade"] * region_area_km2(big) * 1e-6
        except Exception:
            margin = None
        data[name]["water"] = stat(r) | {"km3_per_year": round(inside, 2),
                                         "km3_per_year_with_margin": round(margin, 2) if margin is not None else None,
                                         "area_km2": round(region_area_km2(shape)), "months": r["months"],
                                         "n_eff": round(r["n_eff"]), "record": "2003-2024 (GRACE gap 2017-18)",
                                         "reliable": region_area_km2(shape) > 100000}
    # soil moisture (GLDAS top 10 cm, kg/m2 = mm)
    for name in STATES:
        s = series[(name, "soil_moisture")]
        r = trend_report(s)
        mean = float(s.mean())
        data[name]["soil"] = stat(r) | {"pct_per_decade": round(100 * r["slope_per_decade"] / mean, 2),
                                        "mean": round(mean, 1), "months": r["months"], "n_eff": round(r["n_eff"]),
                                        "record": "2003-2024"}

    # what moves together in each state (correlation engine), and the same pairs compared across states
    from earthpull import engine
    from earthpull.explain import explain, links_facts, overview_facts, state_facts
    LINK_VARS = ["air_temp", "precip", "soil_moisture", "water_storage", "aod_modis_aqua"]
    names = {k: cat[k]["name"] for k in cat}
    link_series = {}
    for name, shape in shapes.items():
        wide = pd.DataFrame({v: series[(name, v)] for v in LINK_VARS if len(series[(name, v)])})
        wide.index = pd.PeriodIndex(wide.index, freq="M")
        wide = wide.loc["2003-01":"2024-12"]
        link_series[name] = wide
        res = engine.run(wide, names, max_lag=3, n_surrogates=500)
        pairs = res["pairs"]
        pt = res["partial_trends"]
        tr = pt[pt.p_alone < 0.05] if len(pt) else pt
        cols_p = ["a", "b", "best_lag", "r", "partial_r", "q", "level", "verdict", "why"]
        cols_t = ["y", "x", "trend_alone_per_decade", "trend_with_x_per_decade", "x_effect_p", "share_of_trend_x_accounts_for", "physics_rule", "verdict"]
        out = {"variables": [{"id": v, "name": names[v]} for v in res["variables"]],
               "pairs": json.loads(pairs[cols_p].to_json(orient="records")) if len(pairs) else [],
               "trend_checks": json.loads(tr[cols_t].to_json(orient="records")) if len(tr) else []}
        w_, s_, e_, n_ = shape.bounds
        ex = explain("links", links_facts(out, {"w": w_, "s": s_, "e": e_, "n": n_}))
        out["explanation"] = {"text": ex["text"], "source": ex["source"]}
        data[name]["links"] = out
        print(name, "links:", int((pairs.level >= 1).sum()) if len(pairs) else 0, "| explanation:", ex["source"], ex.get("errors"))
    compare = []
    for a, b_ in [("air_temp", "soil_moisture"), ("precip", "soil_moisture"), ("precip", "water_storage"),
                  ("soil_moisture", "water_storage"), ("air_temp", "aod_modis_aqua")]:
        tab, summary = engine.compare_regions({n: w[[a, b_]] for n, w in link_series.items() if a in w and b_ in w}, a, b_, 3, None, names)
        compare.append({"a": a, "b": b_, "a_name": names[a], "b_name": names[b_], "summary": summary,
                        "rows": json.loads(tab.to_json(orient="records"))})
        print("compare", a, b_, ":", summary[:110])

    # plain-language explanations, written by an AI model from these numbers and checked by code
    for name in STATES:
        ex = explain("state", state_facts(name, data[name]))
        data[name]["explanation"] = {"text": ex["text"], "source": ex["source"]}
        print(name, "explanation:", ex["source"], ex.get("errors"))
    ov = explain("overview", overview_facts(data))
    print("overview explanation:", ov["source"], ov.get("errors"))
    meta = {"generated": str(date.today()), "regions": "US Census 2024 state outlines (Alaska clipped at 180 deg)",
            "summary": {"text": ov["text"], "source": ov["source"]}, "compare": compare,
            "datasets": {vid: {"name": cat[vid]["name"], "product": f"{cat[vid]['short_name']} {cat[vid].get('version') or ''}".strip(),
                               "variable": cat[vid]["variable"], "caveat": cat[vid].get("caveat", "")} for vid in PERIODS}}
    states_js = {"Alaska": {"code": "AK", "center": [64.2, -152.0], "zoom": 4},
                 "California": {"code": "CA", "center": [37.2, -119.5], "zoom": 6},
                 "Hawaii": {"code": "HI", "center": [20.8, -157.5], "zoom": 7},
                 "Oregon": {"code": "OR", "center": [43.9, -120.6], "zoom": 6},
                 "Washington": {"code": "WA", "center": [47.4, -120.7], "zoom": 7}}
    js = ["// REAL DATA generated by scripts/build_tool_data.py from NASA datasets via the earthpull engine.",
          f"// Generated {meta['generated']}. Do not edit by hand: rerun the script.",
          "window.STATES = " + json.dumps(states_js) + ";",
          "window.META = " + json.dumps(meta, indent=1) + ";",
          "window.STATS = " + json.dumps(data, indent=1) + ";",
          "window.TREND = " + json.dumps({"years": temp_years, "series": temp_series, "baseline": "1991-2020"}) + ";",
          "window.SEASONAL = " + json.dumps({"months": months, "series": seasonal, "period": "2001-2024"}) + ";"]
    with open("Tool/data.js", "w") as f:
        f.write("\n".join(js) + "\n")
    print("wrote Tool/data.js")
    for name in STATES:
        print(name, {k: (v.get("slope_per_decade"), v.get("verdict")) for k, v in data[name].items()})





BOXES = {"Pacific coast (WA, OR, CA)": [-125.0, 32.0, -114.0, 49.0], "Alaska": [-180.0, 51.0, -129.0, 72.0],
         "Hawaii": [-161.0, 18.5, -154.0, 22.5]}


def grids():
    """Per-grid-cell trends inside the West Coast analysis boxes (variables with a global file), plus each state's
    bounding box, for the Map & States tab. Writes Tool/grids.js."""
    import xarray as xr

    from earthpull.core import _open_var, _standardize
    from earthpull.trendmap import trend_map

    grace = sorted((DATA / "raw" / "_global" / "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4").glob("*.nc"))[0]
    sources = {"temp": (lambda: xr.open_dataset(DATA / "cubes" / "air_temp.nc")["T2M"], "1980", "2024",
                        "Air temperature trend", "°C/decade", "MERRA-2, 1980-2024"),
               "water": (lambda: _open_var(grace, "lwe_thickness", "land_mask"), "2003", "2024",
                         "Total water storage trend", "mm/yr", "GRACE/GRACE-FO, 2003-2024 (cm/decade = mm/yr)")}
    out = {}
    for key, (load, a, b, label, unit, note) in sources.items():
        da_all = _standardize(load())
        cells = []
        for bname, (w, s, e, n) in BOXES.items():
            da = da_all.sel(lat=slice(s, n), lon=slice(w, e), time=slice(a, b)).load()
            ds = trend_map(da, 0.10)
            lat, lon = ds.lat.values, ds.lon.values
            dlat, dlon = float(abs(lat[1] - lat[0])), float(abs(lon[1] - lon[0]))
            sl, vd = ds.slope_per_decade.values, ds.verdict.values
            for i in range(len(lat)):
                for j in range(len(lon)):
                    if np.isfinite(sl[i, j]) and vd[i, j] != -9:
                        cells.append([round(float(lat[i]), 3), round(float(lon[j]), 3), round(float(sl[i, j]), 4), int(vd[i, j])])
            print(key, bname, f"{len(lat)}x{len(lon)} cells, {int((vd == 1).sum())} rising, {int((vd == -1).sum())} falling")
        out[key] = {"label": label, "unit": unit, "note": note, "dlat": dlat, "dlon": dlon, "alpha_fdr": 0.10, "cells": cells}
    state_boxes = {name: [round(v, 3) for v in shape.bounds] for name, shape in outlines().items()}
    with open("Tool/grids.js", "w") as f:
        f.write("// Per-grid-cell trends inside the West Coast analysis boxes. Generated by scripts/build_tool_data.py grids\n")
        f.write("window.BOXES = " + json.dumps(BOXES) + ";\n")
        f.write("window.STATE_BOXES = " + json.dumps(state_boxes) + ";\n")
        f.write("window.GRIDS = " + json.dumps(out) + ";\n")
    print("wrote Tool/grids.js", round(sum(len(v["cells"]) for v in out.values())), "cells")


if __name__ == "__main__":
    {"fetch": fetch, "build": build, "grids": grids}[sys.argv[1]]()
