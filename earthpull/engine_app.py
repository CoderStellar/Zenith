"""Correlation engine page: which variables at one place move together, and which links are physically plausible."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from earthpull import engine
from earthpull.core import DATA, BBox, load_catalog, pull

st.title("Correlation engine")
st.caption("For one place: which variables move together, does one variable's trend survive once another is "
           "accounted for, and is a link physically plausible. Fixed statistics and a fixed physics table "
           "(earthpull/links.yaml). No AI. The strongest wording is 'consistent with A influencing B', never 'causes'.")
cat = load_catalog()
NAMES = {k: v["name"] for k, v in cat.items()}
BREAKS = {k: tuple(v.get("breaks", ())) for k, v in cat.items() if v.get("breaks")}
VARS = [v for v in cat if not cat[v].get("event_only")]
PRESETS = {"Maryland / Chesapeake": (-79.585, 37.858, -74.686, 39.809), "Northern India": (70.0, 24.0, 90.0, 32.0)}
last = DATA / "last_run" / "run.json"
if last.exists():
    PRESETS = {"Last pull from 'Explore a region'": tuple(json.loads(last.read_text())["bbox"]), **PRESETS}
PRESETS["Type a box"] = None

c1, c2 = st.columns([2, 3])
where = c1.selectbox("Place", list(PRESETS))
if PRESETS[where] is None:
    cc = c2.columns(4)
    box = tuple(cc[i].number_input(l, -180.0 if i % 2 == 0 else -90.0, 180.0 if i % 2 == 0 else 90.0, d)
                for i, (l, d) in enumerate(zip("WSEN", (-79.585, 37.858, -74.686, 39.809))))
else:
    box = PRESETS[where]
    c2.markdown(f"Box: W {box[0]}, S {box[1]}, E {box[2]}, N {box[3]}")
default_vars = ["air_temp", "aerosol", "precip", "soil_moisture", "evaporation", "surface_air_temp_airs", "no2", "water_storage"]
chosen = st.multiselect("Variables (all on a monthly step)", VARS, default=default_vars, format_func=lambda v: f"{NAMES[v]} ({cat[v]['instrument']})")
c1, c2 = st.columns(2)
y0, y1 = c1.slider("Years", 2003, 2025, (2003, 2024))
max_lag = c2.slider("Look for delays up to (months)", 0, 6, 3)

if st.button("Run the engine", type="primary", disabled=len(chosen) < 2):
    st.session_state["eng_req"] = (box, tuple(chosen), y0, y1, max_lag)
req = st.session_state.get("eng_req")
if req:
    with st.status("Fetching data (cached boxes are instant) and running the tests...", expanded=True) as status:
        log = st.empty()
        lines: list[str] = []

        def show(m, lines=lines, log=log):
            lines.append(m.strip())
            log.text("\n".join(lines[-4:]))

        wide, rep = pull(BBox(*req[0]), f"{req[2]}-01-01", f"{req[3]}-12-31", list(req[1]), progress=show)
        show("running the correlation engine (about 20 seconds)")
        res = engine.run(wide, NAMES, max_lag=req[4], n_surrogates=500, breaks=BREAKS)
        status.update(label="Done", state="complete", expanded=False)
    st.session_state["eng_res"] = (req, res)
    st.session_state.pop("eng_req", None)
    st.rerun()

if "eng_res" not in st.session_state:
    st.stop()
req, res = st.session_state["eng_res"]
pairs, pt = res["pairs"], res["partial_trends"]
if (req[0], tuple(chosen)) != (box, tuple(req[1])):
    st.caption("Results below are for your previous settings. Press 'Run the engine' to update.")
short = lambda v: NAMES.get(v, v).split(" (")[0]

counts = pairs.verdict.str.replace(r" \(.*\)$", "", regex=True).value_counts()
st.markdown("### What moves together here")
k = st.columns(4)
k[0].metric("Pairs tested", len(pairs))
k[1].metric("Consistent with a known mechanism", int((pairs.level == 4).sum()))
k[2].metric("Move together, no known mechanism", int(((pairs.level >= 1) & (pairs.level < 4) & (pairs.rule == "")).sum()))
k[3].metric("No clear link", int((pairs.level == 0).sum()))

v = res["variables"]
M = pd.DataFrame(np.nan, index=v, columns=v)
for r in pairs.itertuples():
    val = r.r if r.level >= 1 else np.nan
    M.loc[r.a, r.b] = M.loc[r.b, r.a] = val
fig = go.Figure(go.Heatmap(z=M.values, x=[short(x) for x in v], y=[short(x) for x in v], zmin=-1, zmax=1,
                           colorscale="RdBu", reversescale=True, colorbar=dict(title="r"),
                           text=np.where(np.isnan(M.values), "", np.round(M.values, 2).astype(str)), texttemplate="%{text}"))
fig.update_layout(height=460, margin=dict(l=10, r=10, t=30, b=10),
                  title="Correlation of month-to-month changes (seasons and trends removed); blank = no clear link")
st.plotly_chart(fig, width="stretch")

show_all = st.toggle("Show pairs with no clear link too", value=False)
tab = pairs if show_all else pairs[pairs.level >= 1]
view = pd.DataFrame({
    "verdict": tab.verdict, "A": tab.a.map(short), "B": tab.b.map(short),
    "delay (months, + = B after A)": tab.best_lag, "r": tab.r.round(2),
    "r after controlling for the rest": tab.partial_r.round(2), "FDR q": tab.q,
    "surrogate p": tab.surrogate_p, "Granger A→B p": tab.granger_a_to_b_p, "Granger B→A p": tab.granger_b_to_a_p,
    "physics rule": tab.why})
st.dataframe(view, hide_index=True, width="stretch",
             column_config={c: st.column_config.NumberColumn(c, format="%.2g") for c in
                            ["FDR q", "surrogate p", "Granger A→B p", "Granger B→A p"]})

st.markdown("### Is each trend still there once another variable is accounted for?")
if len(pt):
    tr = pt[pt.p_alone < engine.ALPHA].copy()
    if tr.empty:
        st.info("No variable has a clear trend here, so there is nothing to explain.")
    else:
        tr = tr.sort_values(["y", "physics_rule"], ascending=[True, False])
        st.dataframe(pd.DataFrame({
            "trend in": tr.y.map(short), "accounting for": tr.x.map(short), "known mechanism": tr.physics_rule,
            "trend per decade alone": tr.trend_alone_per_decade, "trend per decade with X": tr.trend_with_x_per_decade,
            "share X accounts for": (100 * tr.share_of_trend_x_accounts_for).round(0),
            "p of trend with X": tr.p_with_x, "p of X's own effect": tr.x_effect_p,
            "verdict": tr.verdict}), hide_index=True, width="stretch",
            column_config={"trend per decade alone": st.column_config.NumberColumn(format="%.3g"),
                           "trend per decade with X": st.column_config.NumberColumn(format="%.3g"),
                           "share X accounts for": st.column_config.NumberColumn(format="%.0f%%"),
                           "p of trend with X": st.column_config.NumberColumn(format="%.2g"),
                           "p of X's own effect": st.column_config.NumberColumn(format="%.2g")})

st.markdown("### Look at one pair")
opts = [(r.a, r.b) for r in pairs.itertuples()]
a, b = st.selectbox("Pair", opts, format_func=lambda p: f"{short(p[0])} and {short(p[1])}")
row = pairs[(pairs.a == a) & (pairs.b == b)].iloc[0]
det = res["det"]
lag = int(row.best_lag)
x, y = det[a].values, det[b].shift(-lag).values
ok = np.isfinite(x) & np.isfinite(y)
cols = st.columns(2)
sc = go.Figure(go.Scatter(x=x[ok], y=y[ok], mode="markers", marker=dict(size=5, color="#495057", opacity=0.6)))
sc.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10), title=f"r = {row.r:.2f} at delay {lag} months",
                 xaxis_title=f"{short(a)} (change from normal)", yaxis_title=f"{short(b)} (change from normal)")
cols[0].plotly_chart(sc, width="stretch")
z = lambda s: (s - s.mean()) / s.std()
idx = det.index.to_timestamp()
ts = go.Figure([go.Scatter(x=idx, y=z(det[a]), name=short(a), line=dict(width=1, color="#d9480f")),
                go.Scatter(x=idx, y=z(det[b]), name=short(b), line=dict(width=1, color="#1c7ed6"))])
ts.update_layout(height=320, margin=dict(l=10, r=10, t=40, b=10), title="Both, seasons and trends removed (standardised)",
                 legend=dict(orientation="h"))
cols[1].plotly_chart(ts, width="stretch")
st.markdown(f"**{row.verdict}.** {row.why}")

st.markdown("### Compare this pair across places")
st.caption("Same tests, one pair, several regions. Cached regions are instant; a new region fetches its data first.")
from earthpull import news as _news  # gazetteer for place names

place_opts = {k: v for k, v in PRESETS.items() if v is not None}
c1, c2 = st.columns([3, 2])
pick = c1.multiselect("Places", list(place_opts), default=list(place_opts)[:3])
extra = c2.selectbox("Add a place by name", [None] + _news.gazetteer().name.tolist(), index=None,
                     placeholder="Type a country, state or city")
if extra:
    g = _news.gazetteer().set_index("name").loc[extra]
    place_opts[extra] = (float(g.west), float(g.south), float(g.east), float(g.north))
    pick = pick + [extra]
if st.button("Compare across places", disabled=len(pick) < 2):
    series = {}
    with st.status("Fetching each place...", expanded=True) as stt:
        for pl in pick:
            st.write(pl)
            w, _ = pull(BBox(*place_opts[pl]), f"{req[2]}-01-01", f"{req[3]}-12-31", [a, b])
            series[pl] = w
        stt.update(label="Done", state="complete", expanded=False)
    tab, summary = engine.compare_regions(series, a, b, req[4], BREAKS, NAMES)
    st.session_state["cmp"] = ((a, b), tab, summary)
if "cmp" in st.session_state and st.session_state["cmp"][0] == (a, b):
    _, tab, summary = st.session_state["cmp"]
    st.markdown(f"**{summary}**")
    show = tab.copy()
    for c in ("r", "q", "n_eff"):
        if c in show:
            show[c] = show[c].astype(float)
    st.dataframe(show, hide_index=True, width="stretch",
                 column_config={"r": st.column_config.NumberColumn("r", format="%.2f"),
                                "q": st.column_config.NumberColumn("FDR q", format="%.2g"),
                                "n_eff": st.column_config.NumberColumn("effective months", format="%.0f"),
                                "best_lag": st.column_config.NumberColumn("delay (months)")})
    if "r" in tab:
        bars = tab.dropna(subset=["r"])
        fig = go.Figure(go.Bar(x=bars.place, y=bars.r, marker_color=["#2f9e44" if q < engine.ALPHA else "#adb5bd"
                                                                    for q in bars.q]))
        fig.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10), yaxis_range=[-1, 1],
                          title=f"{short(a)} vs {short(b)}: correlation by place (green = clear link)")
        st.plotly_chart(fig, width="stretch")

with st.expander("How the engine decides (fixed rules)"):
    st.markdown("""
1. **Clean up**: remove each month's normal value (seasons) and each variable's straight-line trend, so two
   variables that both just drift do not look linked. Count only the truly independent months (lag-1 autocorrelation).
2. **Move together?** Correlation at delays up to the slider, with a false-discovery correction across every pair and
   delay, and a surrogate test (500 shuffled versions that keep each variable's own rhythm).
3. **Not explained by the rest?** Correlation again after removing every other variable (partial correlation).
4. **Timing**: Granger test both ways. Used to flag one-way timing when no physics rule exists.
5. **Physics**: only pairs in `links.yaml`, with the expected sign and a delay in the expected range, can reach
   *Consistent with A influencing B*. "Same" pairs (two measures of one thing) should agree; "shared" pairs
   (common source) are never called a cause.

**Trend check**: the variable is fitted on time plus the seasonal cycle, once alone and once with X added, using the
same memory-adjusted errors as the trend table on the Explore page. If X has no significant effect of its own, or is
itself mostly a steady trend, the engine says the two cannot be separated.

**Compare across places**: the same pair tested in several regions. A consistent sign supports one mechanism; a sign
that flips with climate (for example wet vs dry regions) is the "same process, opposite direction" pattern.
""")
