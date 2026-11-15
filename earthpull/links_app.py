"""Links page: does a change in place A go with a change in place B? Statistics only, no AI."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from earthpull import link, news
from earthpull.core import BBox, load_catalog

st.title("Links between places")
st.caption("Pick a source place and variable (A) and a target place and variable (B). The tool checks whether "
           "unusual values at A are followed by unusual values at B, and whether the wind blows from A toward B. "
           "Moving together is not proof that A causes B.")
cat = load_catalog()
VARS = [v for v in cat if not cat[v].get("event_only")]
EXAMPLES = {
    "Canadian wildfire smoke → US mid-Atlantic haze": dict(a=(-80, 46, -66, 55), av="aerosol", b=(-79.6, 37.9, -74.7, 39.8),
                                                           bv="aerosol", freq="daily", start=2015, end=2024),
    "Saharan dust → Caribbean haze": dict(a=(-10, 15, 20, 28), av="aerosol", b=(-75, 12, -60, 20), bv="aerosol",
                                         freq="daily", start=2015, end=2024),
    "Himalayan foothills rain → Ganges plain soil moisture": dict(a=(77, 27, 88, 31), av="precip", b=(80, 24, 88, 27),
                                                                  bv="soil_moisture", freq="monthly", start=2003, end=2024),
    "Custom": None,
}
ex = st.selectbox("Start from an example or build your own", list(EXAMPLES))
d = EXAMPLES[ex] or dict(a=(-80, 46, -66, 55), av="aerosol", b=(-79.6, 37.9, -74.7, 39.8), bv="aerosol",
                         freq="monthly", start=2003, end=2024)
gaz = news.gazetteer()
names = gaz.name.tolist()


def box_input(label: str, default: tuple, key: str):
    st.markdown(f"**{label}**")
    how = st.radio("Region", ["Coordinates", "Place name"], horizontal=True, key=f"{key}_how")
    if how == "Place name":
        nm = st.selectbox("Place", names, index=None, placeholder="Type a country, state or city", key=f"{key}_nm")
        if nm:
            r = gaz.set_index("name").loc[nm]
            return (float(r.west), float(r.south), float(r.east), float(r.north))
        return default
    c = st.columns(4)
    vals = [c[i].number_input(lab, -180.0 if i % 2 == 0 else -90.0, 180.0 if i % 2 == 0 else 90.0, float(default[i]),
                              key=f"{key}_{lab}_{ex}") for i, lab in enumerate(["W", "S", "E", "N"])]
    return tuple(vals)


left, right = st.columns(2)
with left:
    a_box = box_input("A · source", d["a"], "a")
    a_var = st.selectbox("Variable at A", VARS, index=VARS.index(d["av"]), key=f"av_{ex}",
                         format_func=lambda v: f"{cat[v]['name']} ({cat[v]['instrument']})")
with right:
    b_box = box_input("B · target", d["b"], "b")
    b_var = st.selectbox("Variable at B", VARS, index=VARS.index(d["bv"]), key=f"bv_{ex}",
                         format_func=lambda v: f"{cat[v]['name']} ({cat[v]['instrument']})")

m = folium.Map(location=[((a_box[1] + a_box[3]) / 2 + (b_box[1] + b_box[3]) / 2) / 2,
                         ((a_box[0] + a_box[2]) / 2 + (b_box[0] + b_box[2]) / 2) / 2], zoom_start=3, tiles="OpenStreetMap")
folium.Rectangle([[a_box[1], a_box[0]], [a_box[3], a_box[2]]], color="#d9480f", fill=True, fill_opacity=0.15, tooltip="A").add_to(m)
folium.Rectangle([[b_box[1], b_box[0]], [b_box[3], b_box[2]]], color="#1c7ed6", fill=True, fill_opacity=0.15, tooltip="B").add_to(m)
folium.PolyLine([[(a_box[1] + a_box[3]) / 2, (a_box[0] + a_box[2]) / 2], [(b_box[1] + b_box[3]) / 2, (b_box[0] + b_box[2]) / 2]],
                color="#495057", dash_array="6").add_to(m)
m.fit_bounds([[min(a_box[1], b_box[1]), min(a_box[0], b_box[0])], [max(a_box[3], b_box[3]), max(a_box[2], b_box[2])]])
st_folium(m, height=320, use_container_width=True, key="link_map", returned_objects=[])

c1, c2, c3 = st.columns(3)
freq = c1.radio("Time step", ["monthly", "daily"], index=0 if d["freq"] == "monthly" else 1, horizontal=True, key=f"f_{ex}",
                help="Daily exists for aerosol (MERRA-2 hourly), rain (IMERG) and NO2 (OMI).")
y0, y1 = c2.slider("Years", 2003, 2025, (d["start"], d["end"]), key=f"y_{ex}")
max_lag = c3.slider(f"Look up to this many {'months' if freq == 'monthly' else 'days'} apart", 1,
                    12 if freq == "monthly" else 15, 3 if freq == "monthly" else 7, key=f"l_{ex}")

if st.button("Test the link", type="primary"):
    st.session_state["link_req"] = (a_box, a_var, b_box, b_var, freq, y0, y1, max_lag)
req = st.session_state.get("link_req")
if req:
    with st.status("Fetching both places and testing...", expanded=True) as status:
        log = st.empty()
        lines: list[str] = []

        def show(msg, lines=lines, log=log):
            lines.append(msg.strip())
            log.text("\n".join(lines[-4:]))

        try:
            res = link.link(BBox(*req[0]), req[1], BBox(*req[2]), req[3], f"{req[5]}-01-01", f"{req[6]}-12-31",
                            freq=req[4], max_lag=req[7], progress=show)
            status.update(label="Done", state="complete", expanded=False)
        except Exception as exc:
            res = {"verdict": f"failed: {exc}"}
            status.update(label=str(exc), state="error")
    st.session_state["link_res"] = (req, res)
    st.session_state.pop("link_req", None)
    st.rerun()

if "link_res" in st.session_state:
    req, res = st.session_state["link_res"]
    st.markdown(f"### {res['verdict']}")
    if "lags" in res and len(res["lags"]):
        unit = "months" if res["freq"] == "monthly" else "days"
        lg = res["lags"]
        colors = ["#2f9e44" if q < 0.05 else "#adb5bd" for q in lg.q]
        fig = go.Figure(go.Bar(x=lg.lag, y=lg.r, marker_color=colors))
        fig.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10),
                          title=f"Correlation by delay (positive = B after A, green = significant after FDR)",
                          xaxis_title=f"delay in {unit}", yaxis_title="r")
        st.plotly_chart(fig, width="stretch")
        a, b = res["aa"], res["ab"]
        z = lambda s: (s - s.mean()) / s.std()
        fig2 = go.Figure([go.Scatter(x=a.index, y=z(a), name="A " + res["source"], line=dict(color="#d9480f", width=1)),
                          go.Scatter(x=b.index, y=z(b), name="B " + res["target"], line=dict(color="#1c7ed6", width=1))])
        fig2.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10), title="Both places, seasonal cycle removed (standardised)",
                           legend=dict(orientation="h"))
        st.plotly_chart(fig2, width="stretch")
        cols = st.columns(2)
        comp = res.get("composite")
        if comp:
            cols[0].markdown("**When A is in its top 10%**")
            cols[0].write(f"B averages {comp['b_during_events']:+.3g} {res['units_b']} vs {comp['b_otherwise']:+.3g} "
                          f"otherwise (anomalies; {comp['n_events']} {unit}; Mann-Whitney p = {comp['p_mannwhitney']:.2g}).")
        w = res.get("wind")
        if w:
            txt = (f"B is {w['distance_km']:.0f} km from A, bearing {w['bearing_deg']:.0f}°. Air about 1.5 km up over A blows "
                   f"toward B in {100 * w['share_toward']:.0f}% of months (mean {w['mean_toward_ms']:+.1f} m/s toward B)")
            if "share_toward_events" in w:
                txt += f", and in {100 * w['share_toward_events']:.0f}% of the months with A events"
            cols[1].markdown("**Wind check (MERRA-2, 850 hPa, monthly)**")
            cols[1].write(txt + ".")
        else:
            cols[1].caption("Wind check unavailable: the wind cubes are not built yet.")
        st.caption(res.get("caveat", ""))
