"""Trend viewer: see a trend, how sure we are, which seasons drive it, how it depends on the start year, and where
inside the region it is happening. Same statistics as the rest of the tool (earthpull.trends)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import xarray as xr
from scipy import stats

from earthpull.core import DATA, BBox, _open_var, _standardize, bbox_of, load_catalog, pull
from earthpull.trends import SEASONS, _ols_ar1, region_area_km2, season_trend, trend_report

st.title("Trend viewer")
st.caption("Pick a place and a variable. The line, its 95% band, the season bars and the map all use the same "
           "memory-adjusted test as the rest of the tool.")
cat = load_catalog()
VARS = [v for v in cat if not cat[v].get("event_only")]
VERDICT_COLOR = {"Clear rise": "#e8590c", "Clear fall": "#1c7ed6"}
GREY = "#adb5bd"

# ------------------------------------------------------------------ region
PRESETS = {"Maryland / Chesapeake": (-79.585, 37.858, -74.686, 39.809), "Northern India": (70.0, 24.0, 90.0, 32.0),
           "Arctic (66.5-90N)": (-180.0, 66.5, 180.0, 90.0), "Whole globe": (-180.0, -90.0, 180.0, 90.0)}
last = DATA / "last_run" / "run.json"
if last.exists():
    PRESETS = {"Last pull from 'Explore a region'": tuple(json.loads(last.read_text())["bbox"]), **PRESETS}
OUTLINES = {  # outlines used in the benchmark tests (scripts/benchmarks.py)
    "Central Valley basins (USGS HUC4)": ("data/boundaries/wbd/huc4_central_valley.geojson", None, None),
    "NW India: Rajasthan, Punjab, Haryana, Delhi": ("data/boundaries/ne/ne_50m_admin_1_states_provinces.geojson", "name",
                                                    ["Rajasthan", "Punjab", "Haryana", "Delhi"]),
    "Greenland": ("data/boundaries/ne/ne_50m_admin_0_countries.geojson", "ADMIN", ["Greenland"]),
    "Antarctica": ("data/boundaries/ne/ne_50m_admin_0_countries.geojson", "ADMIN", ["Antarctica"]),
    "Caspian Sea": ("data/boundaries/ne/ne_50m_geography_marine_polys.geojson", "name", ["Caspian Sea"]),
    "India": ("data/boundaries/ne/ne_50m_admin_0_countries.geojson", "ADMIN", ["India"]),
}

c1, c2, c3 = st.columns([2, 2, 2])
kind = c1.radio("Region", ["Preset box", "US state outline", "Basin / country outline", "Type a box"], horizontal=False)
shape, label = None, ""
if kind == "Preset box":
    label = c2.selectbox("Box", list(PRESETS))
    box = PRESETS[label]
elif kind == "US state outline":
    import geopandas as gpd

    @st.cache_resource
    def _states():
        return gpd.read_file("zip://" + str(DATA / "boundaries" / "cb_2024_us_state_500k.zip")).to_crs(4326)

    stt = _states()
    nm = c2.selectbox("State", sorted(stt.NAME), index=sorted(stt.NAME).index("Wisconsin"))
    shape, label = stt.set_index("NAME").loc[nm].geometry, f"{nm} (Census outline)"
    box = tuple(shape.bounds)
elif kind == "Basin / country outline":
    import geopandas as gpd

    label = c2.selectbox("Outline", list(OUTLINES))
    fpath, col, names = OUTLINES[label]
    g = gpd.read_file(fpath).to_crs(4326)
    if col:
        g = g[g[col].isin(names)]
        if label.startswith("NW India"):
            g = g[g["admin"] == "India"]
    shape = g.union_all()
    box = tuple(shape.bounds)
else:
    cc = c2.columns(2)
    w = cc[0].number_input("W", -180.0, 180.0, -79.585)
    e = cc[1].number_input("E", -180.0, 180.0, -74.686)
    s = cc[0].number_input("S", -90.0, 90.0, 37.858)
    n = cc[1].number_input("N", -90.0, 90.0, 39.809)
    box, label = (w, s, e, n), f"box W {w}, S {s}, E {e}, N {n}"
vid = c3.selectbox("Variable", VARS, index=VARS.index("air_temp"),
                   format_func=lambda v: f"{cat[v]['name']} ({cat[v]['instrument']})")
y0, y1 = c3.slider("Years", 1980, 2026, (2003, 2024))
if c3.button("Show trend", type="primary"):
    st.session_state["viz_req"] = (box, label, vid, y0, y1, kind)
req = st.session_state.get("viz_req")
if not req:
    st.info("Pick a region and a variable, then press Show trend. Regions already pulled load instantly.")
    st.stop()
box, label, vid, y0, y1, kind = req
src = cat[vid]
units = src.get("units", "")


@st.cache_data(show_spinner=False)
def _get(box, label, vid, y0, y1, use_shape):
    sh = shape if use_shape else None
    wide, rep = pull(BBox(*box) if sh is None else None, f"{y0}-01-01", f"{y1}-12-31", [vid], shape=sh)
    return wide, rep


with st.spinner("Fetching (cached regions are instant)..."):
    wide, rep = _get(box, label, vid, y0, y1, shape is not None)
if vid not in wide or wide[vid].notna().sum() < 24:
    st.error(f"No usable data: {rep.iloc[0].get('status') if len(rep) else 'nothing returned'}")
    st.stop()
units = (rep.iloc[0].get("units") if "units" in rep else None) or units
s = wide[vid]
breaks = tuple(src.get("breaks", ()))
r = trend_report(s, breaks)

# ------------------------------------------------------------------ verdict card
st.markdown(f"### {src['name']} · {label} · {y0}-{y1}")
if src.get("caveat"):
    st.caption(f"⚠️ Dataset note from our benchmark tests: {src['caveat']}")
if r.get("too_short"):
    st.warning("Too short to tell: under 10 years of data.")
else:
    k = st.columns(5)
    k[0].metric("Rate per decade", f"{r['slope_per_decade']:+.3g} {units}")
    k[1].metric("95% range", f"{r['ci_low']:+.3g} to {r['ci_high']:+.3g}")
    k[2].metric("p (memory-adjusted)", f"{r['p_ar1']:.2g}")
    pct = r.get("pct_of_mean_per_decade")
    # a percentage only means something for amounts that start at zero (rain, NO2, haze, snow), not for
    # temperatures in kelvin or for anomalies like GRACE water storage
    pct_ok = units not in ("K", "m/s") and vid != "water_storage" and pct == pct
    k[3].metric("% of average per decade", f"{pct:+.1f}%" if pct_ok else "n/a (not a ratio quantity)")
    pchg = r.get("pct_change_over_record")
    if pct_ok and pchg == pchg:
        k[4].metric("Change over the record", f"{pchg:+.0f}%")
    else:
        k[4].metric("Effective months", f"{r['n_eff']:.0f} of {r['months']}")
    if shape is not None and vid == "water_storage":
        from earthpull.trends import LEAKAGE_MARGIN_KM, buffer_km

        # GRACE is in cm, and cm per decade = mm per year, so: mm/yr x km2 x 1e-6 = km3/yr
        inside = r["slope_per_decade"] * region_area_km2(shape) * 1e-6
        try:
            big = buffer_km(shape, LEAKAGE_MARGIN_KM)
            wb, _ = pull(None, f"{y0}-01-01", f"{y1}-12-31", ["water_storage"], shape=big)
            rb = trend_report(wb["water_storage"], breaks)
            margin = rb["slope_per_decade"] * region_area_km2(big) * 1e-6
        except Exception:
            margin = np.nan
        st.info(f"Water volume change: **{inside:+.2f} km³/yr** inside the outline"
                + (f", **{margin:+.2f} km³/yr** including a {LEAKAGE_MARGIN_KM} km margin" if margin == margin else "")
                + ". GRACE's ~3° footprint smears signal across the edge, so the true value is usually between these "
                  "(benchmarks against five papers: inside-outline values recover 64-102% of published trends).")
    verdict = "Clear rise" if (r["p_ar1"] < 0.05 and r["sen_ci_low"] > 0) else "Clear fall" if (
        r["p_ar1"] < 0.05 and r["sen_ci_high"] < 0) else "Likely change, the two methods disagree" if r["p_ar1"] < 0.05 \
        else "No clear trend yet"
    st.markdown(f"**{verdict}.** Month-to-month memory r1 = {r['lag1_autocorr']:.2f}, so {r['months']} months count as "
                f"about {r['n_eff']:.0f} independent ones. Theil-Sen check: {r['sen_per_decade']:+.3g} "
                f"({r['sen_ci_low']:+.3g} to {r['sen_ci_high']:+.3g}).")

tab1, tab2, tab3, tab4 = st.tabs(["Time series", "Seasons and months", "Start-year sensitivity", "Trend map"])

# ------------------------------------------------------------------ 1. time series with trend line and band
with tab1:
    m = s.copy()
    m.index = pd.PeriodIndex(m.index, freq="M")
    idx = pd.period_range(m.index.min(), m.index.max(), freq="M")
    m = m.reindex(idx)
    anom = m - m.groupby(m.index.month).transform("mean")
    ty = np.array([p.year + (p.month - 0.5) / 12 for p in idx])
    ok = np.isfinite(m.to_numpy(float))
    f = _ols_ar1(ty, m.to_numpy(float), ok, breaks)
    tm = ty[ok].mean()
    line = f["slope"] * (ty - tm) + np.nanmean(anom.to_numpy(float))
    tcrit = stats.t.ppf(0.975, max(f["n_eff"] - 6, 1))
    band = tcrit * f["se"] * np.abs(ty - tm)
    x = idx.to_timestamp()
    show_raw = st.toggle("Show raw values instead of anomalies", value=False)
    fig = go.Figure()
    if show_raw:
        fig.add_trace(go.Scatter(x=x, y=m.values, mode="lines", line=dict(color="#495057", width=1), name="monthly"))
    else:
        fig.add_trace(go.Scatter(x=x, y=anom.values, mode="lines", line=dict(color="#868e96", width=1),
                                 name="monthly anomaly (season removed)"))
        from statsmodels.nonparametric.smoothers_lowess import lowess

        okk = np.isfinite(anom.to_numpy(float))
        lw = lowess(anom.to_numpy(float)[okk], ty[okk], frac=0.25, return_sorted=False)
        fig.add_trace(go.Scatter(x=x[okk], y=lw, mode="lines", line=dict(color="#7048e8", width=2, dash="dot"),
                                 name="smooth curve (LOESS): is a straight line fair?"))
        fig.add_trace(go.Scatter(x=np.r_[x, x[::-1]], y=np.r_[line + band, (line - band)[::-1]], fill="toself",
                                 fillcolor="rgba(232,89,12,0.18)", line=dict(width=0), name="95% range of the trend line"))
        fig.add_trace(go.Scatter(x=x, y=line, mode="lines", line=dict(color="#e8590c", width=3), name="trend"))
    for b in tuple(breaks) + tuple(src.get("known_changes", ())):
        fig.add_vline(x=pd.Timestamp(int(b), int(round((b % 1) * 12)) + 1, 1), line_dash="dash", line_color="#2b8a3e",
                      annotation_text="known instrument change")
    fig.update_layout(height=430, margin=dict(l=10, r=10, t=30, b=10), yaxis_title=units, legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")
    st.caption("Grey: each month minus that calendar month's average. Orange: the fitted trend and the range it could "
               "plausibly have. Purple: a smooth curve; if it bends a lot away from the orange line, a single straight "
               "trend is a poor summary.")

# ------------------------------------------------------------------ 2. seasons and months
with tab2:
    rows = []
    for name, months in list(SEASONS.items()) + [(pd.Timestamp(2000, k, 1).strftime("%b"), (k,)) for k in range(1, 13)]:
        t = season_trend(s, months)
        rows.append({"period": name, "years": t["years"], "rate": t.get("slope_per_decade", np.nan),
                     "lo": t.get("ci_low", np.nan), "hi": t.get("ci_high", np.nan), "p": t.get("p", np.nan),
                     "verdict": t["verdict"]})
    sd = pd.DataFrame(rows)
    fig = go.Figure(go.Bar(x=sd.period, y=sd.rate, marker_color=[VERDICT_COLOR.get(v, GREY) for v in sd.verdict],
                           error_y=dict(type="data", symmetric=False, array=sd.hi - sd.rate, arrayminus=sd.rate - sd.lo),
                           hovertext=sd.verdict))
    fig.add_hline(y=0, line_color="#495057")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), yaxis_title=f"{units} per decade",
                      title="Trend of each season's average (left) and of each calendar month (right); "
                            "orange/blue = clear rise/fall, grey = no clear trend yet")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(sd, hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="%.3g") for c in ["rate", "lo", "hi", "p"]})

# ------------------------------------------------------------------ 3. start-year sensitivity
with tab3:
    m = s.copy()
    m.index = pd.PeriodIndex(m.index, freq="M")
    first, lastp = m.dropna().index.min(), m.dropna().index.max()
    rows = []
    for ys in range(first.year, lastp.year - 9):
        t = trend_report(m.loc[pd.Period(f"{ys}-01", "M"):], breaks)
        if not t.get("too_short"):
            rows.append({"start": ys, "rate": t["slope_per_decade"], "lo": t["ci_low"], "hi": t["ci_high"], "p": t["p_ar1"]})
    sy = pd.DataFrame(rows)
    if sy.empty:
        st.info("Needs at least 11 years of data.")
    else:
        fig = go.Figure([go.Scatter(x=np.r_[sy.start, sy.start[::-1]], y=np.r_[sy.hi, sy.lo[::-1]], fill="toself",
                                    fillcolor="rgba(28,126,214,0.15)", line=dict(width=0), name="95% range"),
                         go.Scatter(x=sy.start, y=sy.rate, mode="lines+markers", name="trend",
                                    marker=dict(color=[VERDICT_COLOR["Clear rise"] if p < 0.05 else GREY for p in sy.p]))])
        fig.add_hline(y=0, line_color="#495057")
        fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), xaxis_title="start year (end fixed)",
                          yaxis_title=f"{units} per decade",
                          title="Trend to the end of the record, for every possible start year (coloured = significant)")
        st.plotly_chart(fig, width="stretch")
        st.caption("A robust trend keeps the same sign whatever the start year. If the sign flips, the 'trend' depends "
                   "on cherry-picking the start (IPCC AR5 makes the same point).")

# ------------------------------------------------------------------ 4. trend map
with tab4:
    cube = DATA / "cubes" / f"{vid}.nc"
    grace_file = sorted((DATA / "raw" / "_global" / "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4").glob("*.nc"))
    if not cube.exists() and not (vid == "water_storage" and grace_file):
        st.info("Maps need the variable's global file on this computer. Available now: "
                + ", ".join(sorted([p.stem for p in (DATA / "cubes").glob("*.nc")] + ["water_storage"])) + ". "
                "Build one with: python -m earthpull.cubes <variable>.")
    else:
        from earthpull.trendmap import ALPHA_FDR, trend_map

        @st.cache_data(show_spinner=False)
        def _map(vid, box, y0, y1, use_shape):
            if cube.exists():
                da = xr.open_dataset(cube)[src["variable"]]
            else:
                da = _open_var(grace_file[0], "lwe_thickness", "land_mask")
            da = _standardize(da)
            w, s_, e, n = box
            pad = 1.0
            da = da.sel(lat=slice(s_ - pad, n + pad), lon=slice(w - pad, e + pad),
                        time=slice(f"{y0}-01-01", f"{y1}-12-31")).load()
            ds = trend_map(da, ALPHA_FDR.get(vid, 0.10))
            if use_shape:
                import regionmask

                frac = regionmask.Regions([shape]).mask_3D_frac_approx(ds.lon, ds.lat).isel(region=0, drop=True)
                ds = ds.where(frac > 0)
            return ds

        with st.spinner("Testing every grid cell..."):
            ds = _map(vid, box, y0, y1, shape is not None)
        sig = ds.slope_per_decade.where(ds.verdict.isin([-1, 1]))
        nonsig = xr.where(ds.verdict == 0, 0.0, np.nan)
        lim = float(np.nanpercentile(np.abs(sig.values), 98)) if np.isfinite(sig.values).any() else 1.0
        fig = go.Figure([go.Heatmap(z=nonsig.values, x=ds.lon.values, y=ds.lat.values, showscale=False,
                                    colorscale=[[0, "#dee2e6"], [1, "#dee2e6"]], hoverinfo="skip"),
                         go.Heatmap(z=sig.values, x=ds.lon.values, y=ds.lat.values, zmin=-lim, zmax=lim,
                                    colorscale="RdBu", reversescale=True, colorbar=dict(title=f"{units}/decade"))])
        if shape is not None:
            from shapely.geometry import mapping

            geo = mapping(shape)
            polys = geo["coordinates"] if geo["type"] == "MultiPolygon" else [geo["coordinates"]]
            for poly in polys:
                xs, ys = zip(*poly[0])
                fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="#212529", width=1.5),
                                         showlegend=False, hoverinfo="skip"))
        fig.update_layout(height=520, margin=dict(l=10, r=10, t=40, b=10), yaxis=dict(scaleanchor="x", scaleratio=1),
                          title=f"Trend per grid cell, {y0}-{y1}. Colour = clear trend after FDR (q < "
                                f"{ds.attrs.get('alpha_fdr', 0.1):g}); grey = not significant; blank = no data")
        st.plotly_chart(fig, width="stretch")
        v = ds.verdict.values
        st.caption(f"{int((v == 1).sum())} cells rising, {int((v == -1).sum())} falling, {int((v == 0).sum())} not "
                   "distinguishable. Each cell uses the same memory-adjusted test; Benjamini-Hochberg is applied across "
                   "the cells shown (Wilks 2016).")
