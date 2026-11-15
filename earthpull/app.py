"""Pick a region, see what NASA data exists there, pull it, plot it.

Run:  .venv/bin/streamlit run earthpull/app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import folium
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

from earthpull.core import BBox, check, load_catalog, pull

st.title("Earth data finder")
st.caption("Pick a region: a box, a US state outline, or your own outline (for example a river basin). See which NASA "
           "variables have data there. Pull them as monthly averages over the region.")

DOWNLOAD_HINT = {
    "giovanni": "Tiny. Giovanni's engine averages the box for you (seconds to a few minutes).",
    "harmony": "Small files cut to your box, about 1 file per month (several minutes for 20 years).",
    "MOD13C2": "Large. About 100 MB per month (whole-globe files).",
    "MOD11C3": "Large. About 75 MB per month (whole-globe files).",
    "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4": "46 MB once, reused for every box.",
}
cat = load_catalog()

# ------------------------------------------------------------ last run survives a page refresh
import json

from earthpull.core import DATA

LAST = DATA / "last_run"


def save_last(bbox, start, end, chosen, wide, report, region=""):
    LAST.mkdir(parents=True, exist_ok=True)
    (LAST / "run.json").write_text(json.dumps({"bbox": list(bbox), "start": start, "end": end, "chosen": list(chosen),
                                               "region": region}))
    w = wide.copy()
    w.index = w.index.astype(str)
    w.to_csv(LAST / "wide.csv")
    report.to_csv(LAST / "report.csv", index=False)


if "restored" not in st.session_state and (LAST / "run.json").exists():
    try:
        meta = json.loads((LAST / "run.json").read_text())
        w = pd.read_csv(LAST / "wide.csv", index_col=0)
        w.index = pd.PeriodIndex(w.index, freq="M")
        w.index.name = "month"
        st.session_state["bbox"] = tuple(meta["bbox"])
        st.session_state["years"] = (int(meta["start"][:4]), int(meta["end"][:4]))
        st.session_state["chosen_saved"] = meta["chosen"]
        st.session_state["result"] = (w, pd.read_csv(LAST / "report.csv"), tuple(meta["bbox"]), meta["start"], meta["end"])
        st.session_state["result_region"] = meta.get("region") or ""
    except Exception:
        pass
    st.session_state["restored"] = True

# ------------------------------------------------------------ region input
with st.sidebar:
    st.header("1. Region")
    mode = st.radio("How", ["Draw a box on the map", "Type a bounding box", "Point and radius",
                            "US state (Census outline)", "Upload an outline (GeoJSON)"])
    bbox = st.session_state.get("bbox")
    shape, outline_name = None, ""
    if mode == "Type a bounding box":
        c1, c2 = st.columns(2)
        w = c1.number_input("West", -180.0, 180.0, 70.0)
        e = c2.number_input("East", -180.0, 180.0, 90.0)
        s = c1.number_input("South", -90.0, 90.0, 24.0)
        n = c2.number_input("North", -90.0, 90.0, 32.0)
        bbox = (w, s, e, n)
    elif mode == "Point and radius":
        lat = st.number_input("Latitude", -90.0, 90.0, 38.99)
        lon = st.number_input("Longitude", -180.0, 180.0, -76.94)
        r = st.slider("Half-width (degrees)", 0.5, 10.0, 2.0, 0.5)
        bbox = (max(lon - r, -180), max(lat - r, -90), min(lon + r, 180), min(lat + r, 90))
    elif mode == "US state (Census outline)":
        import geopandas as gpd

        @st.cache_resource
        def _states():
            return gpd.read_file("zip://" + str(DATA / "boundaries" / "cb_2024_us_state_500k.zip")).to_crs(4326)

        stt = _states()
        nm = st.selectbox("State", sorted(stt.NAME), index=sorted(stt.NAME).index("Wisconsin"))
        shape = stt.set_index("NAME").loc[nm].geometry
        outline_name = f"{nm} (US Census 2024 outline)"
    elif mode == "Upload an outline (GeoJSON)":
        import geopandas as gpd

        up = st.file_uploader("GeoJSON polygon(s) in longitude/latitude", type=["geojson", "json"])
        st.caption("For example a river basin from USGS (WBD) or a watershed from your state agency. "
                   "All polygons in the file are merged into one region.")
        if up is not None:
            g = gpd.read_file(up)
            g = g.set_crs(4326) if g.crs is None else g.to_crs(4326)
            shape = g.union_all()
            outline_name = f"{up.name} (uploaded outline)"
    if shape is not None:
        bbox = tuple(round(float(v), 3) for v in shape.bounds)

    st.header("2. Years")
    y0, y1 = st.slider("Range", 1980, 2026, st.session_state.get("years", (2003, 2024)))
    start, end = f"{y0}-01-01", f"{y1}-12-31"

# ------------------------------------------------------------ map
m = folium.Map(location=[20, 0], zoom_start=2, tiles="OpenStreetMap")
Draw(draw_options={"rectangle": True, "polygon": False, "polyline": False, "circle": False,
                   "marker": False, "circlemarker": False}, edit_options={"edit": False}).add_to(m)
if bbox:
    w, s, e, n = bbox
    if shape is not None:
        from shapely.geometry import mapping

        folium.GeoJson(mapping(shape), style_function=lambda _: {"color": "#d9480f", "fillOpacity": 0.15}).add_to(m)
    else:
        folium.Rectangle([[s, w], [n, e]], color="#d9480f", fill=True, fill_opacity=0.1).add_to(m)
    m.fit_bounds([[s, w], [n, e]])
out = st_folium(m, height=420, use_container_width=True, key="map",
                returned_objects=["last_active_drawing"])  # zoom/pan must not rerun the page (it cancels a pull)

if mode == "Draw a box on the map" and out and out.get("last_active_drawing"):
    ring = out["last_active_drawing"]["geometry"]["coordinates"][0]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    bbox = (round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3))
st.session_state["bbox"] = bbox

if not bbox:
    st.info("Draw a rectangle on the map (square icon on the left of the map), or type coordinates in the sidebar.")
    st.stop()

try:
    box = BBox(*bbox)
    BBox.parse(",".join(map(str, bbox)))  # validates order and ranges
except ValueError as exc:
    st.error(str(exc))
    st.stop()

w, s, e, n = bbox
region_text = outline_name or f"box W {w}, S {s}, E {e}, N {n}"
st.subheader(f"{'Outline: ' + outline_name if outline_name else f'Box: W {w}, S {s}, E {e}, N {n}'}  ·  {y0} to {y1}")
if shape is not None:
    st.caption("Values are averaged over the outline, each grid cell weighted by its share inside it. Giovanni's fast "
               "averaging only takes rectangles, so the first pull of an outline cuts files instead (a few minutes).")
if (e - w) < 1 or (n - s) < 1:
    st.warning("This box is under 1 degree wide. AIRS (1 deg) and GRACE (about 3 deg real resolution) "
               "will be unreliable or fail. Make it bigger for those.")

# ------------------------------------------------------------ availability
@st.cache_data(show_spinner=False, ttl=3600)
def cached_check(bbox, start, end):
    return check(BBox(*bbox), start, end)

with st.spinner("Asking NASA's catalog what exists here..."):
    avail = cached_check(bbox, start, end)

avail["download"] = [DOWNLOAD_HINT.get(cat[i]["short_name"], DOWNLOAD_HINT.get(cat[i]["method"], ""))
                     for i in avail["id"]]
st.markdown("### What's available")
st.dataframe(
    avail[["available", "name", "source", "coverage", "cadence", "domain", "method", "download", "id"]],
    hide_index=True, width="stretch",
    column_config={"available": st.column_config.CheckboxColumn("Data?"),
                   "domain": st.column_config.TextColumn("Covers", help="land-only products are blank over ocean")},
)

# ------------------------------------------------------------ pull + plot
ok_ids = avail.loc[avail["available"], "id"].tolist()
light = [i for i in ok_ids if cat[i]["method"] in ("giovanni", "harmony")]
if "water_storage" in ok_ids:
    light.append("water_storage")

st.markdown("### Pull the data")
saved = [v for v in st.session_state.get("chosen_saved", []) if v in ok_ids]
chosen = st.multiselect("Variables", ok_ids, default=saved or light,
                        format_func=lambda i: f"{cat[i]['name']} ({cat[i]['instrument']})")
heavy = [i for i in chosen if cat[i]["method"] == "download" and i != "water_storage"]
daily = [i for i in chosen if cat[i]["cadence"] == "daily" and cat[i]["method"] != "giovanni"]
if heavy:
    st.warning(f"{', '.join(heavy)}: whole-globe MODIS files, roughly 1 GB per year per variable. Slow the first time.")
if daily:
    st.warning(f"{', '.join(daily)}: daily files, about 365 per year. Slow the first time.")

SPEED = {"giovanni": (0, "usually under a minute"),
         "download": (1, "about a minute (GRACE) or long (MODIS, ~100 MB per month)"),
         "harmony": (2, "several minutes: NASA cuts one file per month")}


def _order(i):
    rank = SPEED[cat[i]["method"]][0] + (3 if i in heavy else 0)
    return (rank, i)


def _chart(series: pd.Series, vid: str, units: str):
    s = series.copy()
    s.index = s.index.to_timestamp() if hasattr(s.index, "to_timestamp") else pd.to_datetime(s.index.astype(str))
    fig = px.line(x=s.index, y=s.values, title=f"{cat[vid]['name']} ({cat[vid]['instrument']})",
                  labels={"x": "", "y": units})
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
    return fig


if st.button("Pull", type="primary", disabled=not chosen):
    st.session_state["pull_request"] = (tuple(chosen), bbox, start, end, region_text)

# The request survives reruns (any click restarts the script), so a pull resumes instead of vanishing.
# Variables already fetched come back from the local cache in seconds.
req = st.session_state.get("pull_request")
if req and req[1:] != (bbox, start, end, region_text):
    st.session_state.pop("pull_request")  # region or years changed: drop the old request
    req = None
if req:
    todo = sorted(req[0], key=_order)
    st.info(f"Fetching {len(todo)} variables, fastest first. Each chart appears as soon as its data arrives. "
            "Anything pulled before for this exact box and years comes from the local cache in seconds.")
    bar = st.progress(0.0, text=f"0 of {len(todo)} done")
    cols = st.columns(2)
    series, rows = {}, []
    for k, vid in enumerate(todo):
        label = f"{k + 1}/{len(todo)} · {cat[vid]['name']} ({cat[vid]['instrument']})"
        with st.status(f"{label} · {SPEED[cat[vid]['method']][1]}", expanded=True) as box_status:
            log = st.empty()
            lines: list[str] = []

            def show(msg: str, lines=lines, log=log):
                msg = msg.strip()
                if lines and "NASA is processing" in msg and "NASA is processing" in lines[-1]:
                    lines[-1] = msg  # update the percentage in place
                else:
                    lines.append(msg)
                log.text("\n".join(lines[-4:]))

            wide, rep = pull(box, start, end, [vid], include_daily=True, progress=show, shape=shape)
            row = rep.iloc[0].to_dict()
            rows.append(row)
            ok = row.get("status") == "ok" and vid in wide.columns
            box_status.update(label=f"{label} · {'done' if ok else row.get('status')}",
                              state="complete" if ok else "error", expanded=not ok)
        if ok:
            series[vid] = wide[vid]
            cols[(len(series) - 1) % 2].plotly_chart(_chart(wide[vid], vid, row.get("units") or ""), width="stretch")
        bar.progress((k + 1) / len(todo), text=f"{k + 1} of {len(todo)} done")
    out = pd.DataFrame(series)
    out.index.name = "month"
    st.session_state["result"] = (out, pd.DataFrame(rows), bbox, start, end)
    st.session_state["result_region"] = region_text
    save_last(bbox, start, end, req[0], out, pd.DataFrame(rows), region_text)
    st.session_state.pop("pull_request", None)
    st.rerun()

if "result" in st.session_state:
    wide, report, rbbox, rstart, rend = st.session_state["result"]
    if rbbox != bbox or rstart != start or rend != end:
        st.caption("Showing the last pull, which was for a different box or years. Press Pull to refresh.")
    st.dataframe(report, hide_index=True, width="stretch")
    if not wide.empty:
        df = wide.copy()
        df.index = df.index.to_timestamp() if hasattr(df.index, "to_timestamp") else pd.to_datetime(df.index.astype(str))
        units = dict(zip(report["id"], report.get("units", pd.Series(dtype=str))))
        cols = st.columns(2)
        for k, vid in enumerate(wide.columns):
            cols[k % 2].plotly_chart(_chart(wide[vid], vid, units.get(vid) or ""), width="stretch")
        from earthpull.core import export_csv

        st.download_button("Download CSV (with units and dataset names)",
                           export_csv(wide, report, st.session_state.get("result_region") or f"box {rbbox}", rstart, rend)
                           .encode(), "earth_data.csv", "text/csv")

        st.markdown("### Trends")
        from earthpull.trends import analyze

        tr = analyze(wide, units, {v: tuple(cat[v].get("breaks", ())) for v in wide.columns if v in cat})
        for c in ["slope_per_decade", "ci_low", "ci_high", "sen_per_decade", "sen_ci_low", "sen_ci_high", "q_fdr",
                  "p_ttest", "lag1_autocorr", "n_eff", "years_needed"]:
            if c not in tr:
                tr[c] = np.nan
        show = tr[["verdict", "id", "slope_per_decade", "ci_low", "ci_high", "units", "q_fdr", "sen_per_decade",
                   "sen_ci_low", "sen_ci_high", "lag1_autocorr", "n_eff", "p_ttest", "months", "years_needed"]].copy()
        show.insert(1, "variable", [f"{cat[v]['name']} ({cat[v]['instrument']})" for v in show.id])
        st.dataframe(show.drop(columns="id"), hide_index=True, width="stretch",
                     column_config={"slope_per_decade": st.column_config.NumberColumn("rate per decade", format="%.3g"),
                                    "ci_low": st.column_config.NumberColumn("95% CI low", format="%.3g"),
                                    "ci_high": st.column_config.NumberColumn("95% CI high", format="%.3g"),
                                    "q_fdr": st.column_config.NumberColumn("q (memory-adjusted, FDR)", format="%.2g"),
                                    "sen_per_decade": st.column_config.NumberColumn("Theil-Sen per decade", format="%.3g"),
                                    "sen_ci_low": st.column_config.NumberColumn("Theil-Sen 95% low", format="%.3g"),
                                    "sen_ci_high": st.column_config.NumberColumn("Theil-Sen 95% high", format="%.3g"),
                                    "lag1_autocorr": st.column_config.NumberColumn("month-to-month memory (r1)", format="%.2f"),
                                    "n_eff": st.column_config.NumberColumn("effective months", format="%.0f"),
                                    "p_ttest": st.column_config.NumberColumn("t-test p (ignores memory)", format="%.2g"),
                                    "years_needed": st.column_config.NumberColumn("years needed to detect", format="%.0f")})
        st.caption("Rate per decade from a straight-line fit together with the seasonal cycle. Its 95% range and "
                   "p-value count neighbouring months as partly the same information (AR(1) effective sample size, "
                   "as IPCC AR6 does). 'Clear' needs this test to pass after Benjamini-Hochberg correction across the "
                   "variables shown AND a Theil-Sen slope with the same correction to agree. The t-test column "
                   "ignores that memory and is shown only for comparison. 'Check back' years follow Weatherhead et al. "
                   "(1998). Ranked by change over the record relative to normal month-to-month noise.")
