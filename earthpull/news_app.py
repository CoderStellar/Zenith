"""News lens page: news headline -> place -> NASA data around that place and time. No AI: rules only."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from earthpull import news
from earthpull.core import BBox, load_catalog

st.title("News lens")
st.caption("Search the news or pick a live natural event. The tool finds the places named in the headlines, "
           "picks variables from a fixed keyword table, and checks NASA data there. No AI is used. "
           "It shows what changed in the data, not why.")
cat = load_catalog()
TOPICS = news.topics()
EONET_TOPIC = {"Wildfires": "wildfire", "Severe Storms": "flood", "Floods": "flood", "Volcanoes": "volcano",
               "Dust and Haze": "air_pollution", "Sea and Lake Ice": "ice", "Drought": "drought",
               "Temperature Extremes": "heat", "Landslides": "flood", "Snow": "ice"}

# ------------------------------------------------------------------ choose a source
src_mode = st.radio("Start from", ["Latest environment news", "Search the news", "Live natural events (NASA EONET)"],
                    horizontal=True)


@st.cache_data(ttl=1800, show_spinner=False)
def _feed(days: int) -> pd.DataFrame:
    return news.latest_environment_news(days)


if src_mode == "Latest environment news":
    c1, c2 = st.columns([1, 3])
    days = c1.selectbox("From the last", [3, 7, 14], index=1, format_func=lambda d: f"{d} days")
    with st.spinner("Collecting environment headlines (one search per topic)..."):
        feed = _feed(days)
    if feed.empty:
        st.info("No headlines with a recognisable place right now.")
        st.stop()
    kinds = c2.multiselect("Topics", sorted(feed.topic_label.unique()), default=sorted(feed.topic_label.unique()))
    feed = feed[feed.topic_label.isin(kinds)].reset_index(drop=True)
    st.caption("Click a row to check that place. Each headline is tied to the most specific place it names "
               "(city, then state, then country), matched by exact name.")
    sel = st.dataframe(feed[["date", "topic_label", "place", "title", "source", "link"]], hide_index=True,
                       height=330, width="stretch", on_select="rerun", selection_mode="single-row", key="feed_sel",
                       column_config={"topic_label": "topic",
                                      "link": st.column_config.LinkColumn("link", display_text="open")})
    rows = sel.selection.rows if sel and sel.selection else []
    if not rows:
        st.info("Pick a headline above.")
        st.stop()
    r = feed.iloc[rows[0]]
    bbox = (r.west, r.south, r.east, r.north)
    topic = r.topic
    default_date = pd.Timestamp(r.date).date()
    place_label = f"{r.place} · {r.title}"
    st.success(f"**{r.place}** ({r.kind}) · {r.topic_label} · {r.date}  \n{r.title}")

elif src_mode == "Search the news":
    c1, c2, c3 = st.columns([3, 1, 1])
    query = c1.text_input("Search the news", value=st.session_state.get("q", "diwali pollution"))
    days = c2.selectbox("Last", [7, 14, 30, 90], index=2, format_func=lambda d: f"{d} days")
    c3.write("")
    if c3.button("Search", type="primary") or "news" not in st.session_state:
        with st.spinner("Searching Google News..."):
            try:
                st.session_state["news"] = news.search_news(query, days)
            except Exception as exc:
                st.error(f"News search failed: {exc}")
                st.session_state["news"] = pd.DataFrame(columns=["date", "title", "source", "link"])
        st.session_state["q"] = query
        for k in ("place_pick", "impact"):
            st.session_state.pop(k, None)
    df = st.session_state["news"]
    if df.empty:
        st.info("No headlines found. Try other words.")
        st.stop()

    found = news.match_topics(" ".join(df.title.head(50)) + " " + st.session_state.get("q", ""))
    topic_ids = list(TOPICS)
    topic = st.selectbox("Topic (from the keyword table)", topic_ids,
                         index=topic_ids.index(found[0]) if found else 0,
                         format_func=lambda t: TOPICS[t]["label"] + ("  ← matched" if t in found else ""))
    df = news.filter_headlines(df, topic)

    places = news.find_places(df.title.tolist())
    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"**{len(df)} headlines**")
        st.dataframe(df[["date", "title", "source", "link"]], hide_index=True, height=300, width="stretch",
                     column_config={"link": st.column_config.LinkColumn("link", display_text="open")})
    with right:
        st.markdown("**Places named in the headlines**")
        if places.empty:
            st.info("No known place names in these headlines. Use the region page with your own box.")
            st.stop()
        st.dataframe(places[["name", "kind", "country", "mentions"]], hide_index=True, height=300, width="stretch")
    pick = st.selectbox("Place to check", places.name.tolist(), key="place_pick")
    row = places.set_index("name").loc[pick]
    bbox = (row.west, row.south, row.east, row.north)
    mentions = df[df.title.str.contains(pick, regex=False)]
    default_date = pd.to_datetime(pd.Series(mentions.date if len(mentions) else df.date)).median().date()
    place_label = pick
else:
    days = st.selectbox("Events from the last", [7, 14, 30, 60], index=2, format_func=lambda d: f"{d} days")
    try:
        ev = news.eonet_events(days)
    except Exception as exc:
        st.error(f"EONET failed: {exc}")
        st.stop()
    if ev.empty:
        st.info("No events.")
        st.stop()
    cats = sorted(ev.category.unique())
    pick_cat = st.multiselect("Kinds", cats, default=[c for c in cats if c != "Wildfires"] or cats)
    ev = ev[ev.category.isin(pick_cat)].reset_index(drop=True)
    st.dataframe(ev, hide_index=True, height=260, width="stretch",
                 column_config={"link": st.column_config.LinkColumn("link", display_text="source")})
    if ev.empty:
        st.stop()
    i = st.selectbox("Event to check", range(len(ev)), format_func=lambda k: f"{ev.date[k]} · {ev.title[k]}")
    e = ev.iloc[i]
    h = st.slider("Box half-width (degrees)", 0.5, 5.0, 1.5, 0.5)
    bbox = (max(e.lon - h, -180), max(e.lat - h, -90), min(e.lon + h, 180), min(e.lat + h, 90))
    topic = EONET_TOPIC.get(e.category, "flood")
    st.caption(f"Topic from the event kind: **{TOPICS[topic]['label']}**")
    default_date = pd.Timestamp(e.date).date()
    place_label = e.title

# ------------------------------------------------------------------ map + settings
w, s, ee, n = (round(float(v), 3) for v in bbox)
m = folium.Map(location=[(s + n) / 2, (w + ee) / 2], zoom_start=5, tiles="OpenStreetMap")
folium.Rectangle([[s, w], [n, ee]], color="#d9480f", fill=True, fill_opacity=0.15, tooltip=place_label).add_to(m)
m.fit_bounds([[s, w], [n, ee]])
st_folium(m, height=300, use_container_width=True, key="news_map", returned_objects=[])

tp = TOPICS[topic]
c1, c2, c3 = st.columns(3)
mode = c1.radio("Check", ["event", "longterm"], index=0 if tp["mode"] == "event" else 1,
                format_func=lambda x: {"event": "Event: this window vs other years",
                                       "longterm": "Long-term trend at this place"}[x])
ev_date = c2.date_input("Event date", value=default_date, max_value=date.today())
win = c3.slider("Window (± days, daily data)", 3, 15, 7) if mode == "event" else None
vars_ = st.multiselect("Variables (from the keyword table)", [v for v in cat if not cat[v].get("event_only")],
                       default=tp["variables"], format_func=lambda v: f"{cat[v]['name']} ({cat[v]['instrument']})")
st.caption(f"Box: W {w}, S {s}, E {ee}, N {n}. Recent events use near-real-time versions where they exist "
           "(OMI NO2 v004, IMERG Late daily). A new place takes a few minutes the first time, then it is cached.")

if st.button("Check the data", type="primary", disabled=not vars_):
    st.session_state["impact_req"] = (tuple(vars_), bbox, str(ev_date), mode, win)
req = st.session_state.get("impact_req")
if req and req[1:] != (bbox, str(ev_date), mode, win):
    st.session_state.pop("impact_req")
    req = None


def bar_chart(r: dict, ev_year: int):
    py = dict(sorted(r["per_year"].items()))
    colors = ["#d9480f" if y == ev_year else "#adb5bd" for y in py]
    fig = go.Figure(go.Bar(x=list(py), y=list(py.values()), marker_color=colors))
    if r.get("baseline_mean") is not None and np.isfinite(r.get("baseline_mean", np.nan)):
        fig.add_hline(y=r["baseline_mean"], line_dash="dot", annotation_text="earlier-years average")
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10),
                      title=f"{r['name']} · {r['window']}", yaxis_title=r.get("units", ""))
    return fig


def trend_chart(r: dict):
    s = r["series"]
    x = s.index.to_timestamp()
    fig = go.Figure(go.Scatter(x=x, y=s.values, mode="lines", line=dict(color="#495057", width=1)))
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=10), title=r["name"], yaxis_title=r.get("units", ""))
    return fig


if req:
    rvars, rbbox, rdate, rmode, rwin = req
    box = BBox(*rbbox)
    results = []
    for k, vid in enumerate(rvars):
        with st.status(f"{k + 1}/{len(rvars)} · {cat[vid]['name']}", expanded=True) as status:
            log = st.empty()
            lines: list[str] = []

            def show(msg, lines=lines, log=log):
                msg = msg.strip()
                if lines and "processing" in msg and "processing" in lines[-1]:
                    lines[-1] = msg
                else:
                    lines.append(msg)
                log.text("\n".join(lines[-4:]))

            try:
                r = (news.event_impact(box, vid, rdate, rwin, progress=show) if rmode == "event"
                     else news.longterm(box, vid))
            except Exception as exc:
                r = {"id": vid, "name": cat[vid]["name"], "verdict": f"failed: {exc}"}
            results.append(r)
            status.update(label=f"{k + 1}/{len(rvars)} · {r.get('name', vid)} · {r.get('verdict', '')}",
                          state="complete", expanded=False)
    st.session_state["impact"] = (req, results)
    st.session_state.pop("impact_req", None)
    st.rerun()

if "impact" in st.session_state:
    (rvars, rbbox, rdate, rmode, rwin), results = st.session_state["impact"]
    if (tuple(rbbox), rdate) != (tuple(bbox), str(ev_date)):
        st.caption("Results below are for your previous selection. Press 'Check the data' for this one.")
    st.markdown(f"### What the data shows around {rdate}")
    cols = st.columns(2)
    for k, r in enumerate(results):
        with cols[k % 2]:
            st.markdown(f"**{r.get('name', r['id'])}** · {r.get('source', '')}")
            st.markdown(f"> {r.get('verdict', '')}")
            if rmode == "event" and r.get("per_year"):
                if r.get("event_value") is not None and r.get("change_pct") is not None and np.isfinite(r["change_pct"]):
                    st.caption(f"Event window: {r['event_value']:.3g} {r['units']} · earlier-years average "
                               f"{r['baseline_mean']:.3g} · difference {r['change_pct']:+.0f}% · z = {r['z']:.1f}")
                st.plotly_chart(bar_chart(r, pd.Timestamp(rdate).year), width="stretch")
            elif rmode == "longterm" and r.get("series") is not None and len(r["series"]):
                if r.get("slope_per_decade") is not None:
                    st.caption(f"Sen slope {r['slope_per_decade']:+.3g} {r['units']} per decade · "
                               f"Mann-Kendall (Hamed-Rao) p = {r['p']:.3f} · {r['months']} months")
                st.plotly_chart(trend_chart(r), width="stretch")
    st.caption("Rules: 'much higher/lower' = 2+ standard deviations from earlier years, 'higher/lower' = 1 to 2, "
               "otherwise 'within the normal range'. At least 5 earlier years are needed. "
               "This shows what changed, not why.")
