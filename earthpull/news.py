"""News lens: from a news search to a NASA-data check of the places in the news. No AI anywhere.

1. search_news()   Google News RSS for the query (no key)            -> headlines with dates
   eonet_events()  NASA EONET open natural events (no key)          -> events with coordinates
2. find_places()   exact-name match against countries, states/provinces and cities (gazetteer)
3. match_topics()  keyword table in topics.yaml                     -> which variables to check
4. event_impact()  event window vs the same window in earlier years -> how unusual, fixed wording
   longterm()      trend over the whole record (Sen slope, Mann-Kendall)

The tool reports what changed in the data around the place and time. It never says why.
"""
from __future__ import annotations

import io
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .core import DATA, BBox, _clip_dates, _fetch_giovanni, _raw_dir, load_catalog, login, pull

UA = {"User-Agent": "earthpull/0.1 (hackathon research tool)"}
TOPICS = Path(__file__).with_name("topics.yaml")
GAZ = DATA / "gazetteer.parquet"
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
CITY_HALF_WIDTH = 1.5  # degrees around a city: big enough for the coarse satellite grids

# Words that are also place names but usually are not places in headlines.
STOP = {"Of", "Mobile", "Reading", "Bath", "March", "Nice", "Split", "Best", "Hope", "Florence", "Victoria",
        "Jordan", "Chad", "Georgia", "Independence", "Paris", "Same", "Male", "Most", "Bay", "Union", "Delta",
        "Orange", "Gold Coast", "Mobile", "Normal", "Marathon", "Sale", "Deal", "Wells", "Bristol", "Phoenix",
        "Rio Grande", "Columbia", "Colorado", "Amazon", "Mississippi", "Missouri", "Niger", "Congo River"}  # rivers more often than cities
ALIASES = {"US": "United States of America", "U.S.": "United States of America", "USA": "United States of America",
           "America": "United States of America", "UK": "United Kingdom", "U.K.": "United Kingdom",
           "Britain": "United Kingdom", "Russia": "Russia", "Congo": "Democratic Republic of the Congo",
           "DRC": "Democratic Republic of the Congo", "UAE": "United Arab Emirates", "Delhi": "New Delhi"}


# ------------------------------------------------------------------ 1. sources

def search_news(query: str, days: int = 30, lang: str = "en-US", country: str = "US") -> pd.DataFrame:
    q = urllib.parse.quote(f"{query} when:{days}d")
    url = f"https://news.google.com/rss/search?q={q}&hl={lang}&gl={country}&ceid={country}:{lang.split('-')[0]}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        root = ET.fromstring(r.read())
    rows = []
    for it in root.iter("item"):
        title = it.findtext("title") or ""
        src = it.findtext("source") or ""
        if src and title.endswith(f" - {src}"):
            title = title[: -len(src) - 3]
        when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc)
        rows.append({"date": when.date(), "time": when.strftime("%Y-%m-%dT%H:%M:%SZ"),  # exact UTC time, shown in the reader's zone
                     "title": title, "source": src, "link": it.findtext("link")})
    return pd.DataFrame(rows).sort_values("date", ascending=False, ignore_index=True) if rows else \
        pd.DataFrame(columns=["date", "time", "title", "source", "link"])


def eonet_events(days: int = 30, category: str | None = None) -> pd.DataFrame:
    """NASA Earth Observatory Natural Event Tracker: wildfires, storms, volcanoes, dust, floods..."""
    params = {"status": "all", "days": days, "limit": 300}
    if category:
        params["category"] = category
    url = "https://eonet.gsfc.nasa.gov/api/v3/events?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        d = json.load(r)
    rows = []
    for e in d.get("events", []):
        g = e["geometry"][-1]
        c = g["coordinates"]
        if g["type"] == "Point":
            lon, lat = c
        else:  # polygon: centre of its outer ring
            ring = np.array(c[0])
            lon, lat = ring[:, 0].mean(), ring[:, 1].mean()
        rows.append({"date": g["date"][:10], "category": e["categories"][0]["title"], "title": e["title"],
                     "lat": round(float(lat), 3), "lon": round(float(lon), 3),
                     "link": (e.get("sources") or [{}])[0].get("url", "")})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ 2. places

def _largest_bbox(geom: dict) -> tuple[float, float, float, float]:
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    best, best_area = None, -1.0
    for poly in polys:
        ring = np.asarray(poly[0])
        x, y = ring[:, 0], ring[:, 1]
        area = 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
        if area > best_area:
            best, best_area = (x.min(), y.min(), x.max(), y.max()), area
    return tuple(round(float(v), 3) for v in best)


def build_gazetteer() -> pd.DataFrame:
    """Natural Earth countries and states/provinces (public domain), GeoNames cities over 100k (CC BY 4.0)."""
    rows = []
    for layer, kind in [("ne_50m_admin_0_countries.geojson", "country"),
                        ("ne_50m_admin_1_states_provinces.geojson", "state")]:
        with urllib.request.urlopen(urllib.request.Request(NE + layer, headers=UA), timeout=120) as r:
            fc = json.load(r)
        for f in fc["features"]:
            p = f["properties"]
            name = p.get("NAME") or p.get("name")
            if not name or not f.get("geometry"):
                continue
            w, s, e, n = _largest_bbox(f["geometry"])
            country = p.get("ADMIN") or p.get("admin") or name
            names = {name, p.get("NAME_LONG") or name, p.get("ADMIN") or name} if kind == "country" else {name}
            for nm in names:
                rows.append({"name": nm, "kind": kind, "country": country, "west": w, "south": s,
                             "east": e, "north": n, "population": float(p.get("POP_EST") or 0)})
    url = "https://download.geonames.org/export/dump/cities15000.zip"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    cols = ["id", "name", "ascii", "alt", "lat", "lon", "fclass", "fcode", "cc", "cc2", "a1", "a2", "a3", "a4",
            "population", "elev", "dem", "tz", "mod"]
    c = pd.read_csv(z.open("cities15000.txt"), sep="\t", names=cols, usecols=["name", "lat", "lon", "cc", "population"],
                    keep_default_na=False, low_memory=False)
    c = c[c.population >= 100_000]
    h = CITY_HALF_WIDTH
    rows += [{"name": r.name, "kind": "city", "country": r.cc, "west": max(r.lon - h, -180), "south": max(r.lat - h, -90),
              "east": min(r.lon + h, 180), "north": min(r.lat + h, 90), "population": float(r.population)}
             for r in c.itertuples()]
    g = pd.DataFrame(rows)
    g = g[g.name.str.len() >= 3]
    # one entry per name: countries win over states win over cities; then the most populous
    g["rank"] = g.kind.map({"country": 0, "state": 1, "city": 2})
    g = g.sort_values(["rank", "population"], ascending=[True, False]).drop_duplicates("name").drop(columns="rank")
    GAZ.parent.mkdir(parents=True, exist_ok=True)
    g.reset_index(drop=True).to_parquet(GAZ)
    return g


def gazetteer() -> pd.DataFrame:
    return pd.read_parquet(GAZ) if GAZ.exists() else build_gazetteer()


_PATTERN = None


def find_places(titles: list[str]) -> pd.DataFrame:
    """Exact, case-sensitive name matches in headlines. Counted once per headline."""
    global _PATTERN
    g = gazetteer().set_index("name")
    if _PATTERN is None:
        names = sorted((n for n in g.index if n not in STOP), key=len, reverse=True)
        names += [a for a in ALIASES if a not in g.index]
        _PATTERN = re.compile(r"(?<![\w.])(" + "|".join(re.escape(n) for n in names) + r")(?![\w])")
    hits: dict[str, int] = {}
    for t in titles:
        for m in set(_PATTERN.findall(t)):
            nm = ALIASES.get(m, m)
            if nm in g.index:
                hits[nm] = hits.get(nm, 0) + 1
    if not hits:
        return pd.DataFrame(columns=["name", "kind", "country", "mentions", "west", "south", "east", "north"])
    out = g.loc[list(hits)].reset_index()
    out["mentions"] = out.name.map(hits)
    return out.sort_values(["mentions", "population"], ascending=False, ignore_index=True)[
        ["name", "kind", "country", "mentions", "west", "south", "east", "north"]]


# ------------------------------------------------------------------ 3. topics

def _topics_raw() -> dict:
    return yaml.safe_load(TOPICS.read_text())


def topics() -> dict:
    return {k: v for k, v in _topics_raw().items() if not k.startswith("_")}


def _global_exclude() -> list[str]:
    return _topics_raw().get("_exclude_all", [])


def _has_word(text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def match_topics(text: str) -> list[str]:
    """Topic ids whose keywords appear in the text (case-insensitive) and whose excludes do not."""
    t = text.lower()
    found = []
    if _has_word(t, _global_exclude()):
        return found
    for tid, tp in topics().items():
        if any(x in t for x in tp.get("exclude", [])):
            continue
        if tp.get("require_any") and not _has_word(t, tp["require_any"]):
            continue
        if any(re.search(rf"\b{re.escape(k)}", t) for k in tp["keywords"]):
            found.append(tid)
    return found


def filter_headlines(news: pd.DataFrame, topic_id: str) -> pd.DataFrame:
    tp = topics()[topic_id]
    glob = _global_exclude()
    keep = [not any(x in t.lower() for x in tp.get("exclude", [])) and not _has_word(t.lower(), glob)
            for t in news.title]
    return news[keep].reset_index(drop=True)


# ------------------------------------------------------------------ 4. impact

def verdict(z: float, rank_above: int, n_years: int) -> str:
    """Fixed wording from fixed cut-offs."""
    if n_years < 5 or not np.isfinite(z):
        return "Not enough earlier years to compare"
    if z >= 2:
        word = "Much higher than usual"
    elif z >= 1:
        word = "Higher than usual"
    elif z <= -2:
        word = "Much lower than usual"
    elif z <= -1:
        word = "Lower than usual"
    else:
        word = "Within the normal range"
    return f"{word} (higher than {rank_above} of {n_years} earlier years)"


def _window_values(src: dict, bbox: BBox, centers: list[pd.Timestamp], window_days: int, cache: Path,
                   progress=None) -> dict[int, tuple[float, float]]:
    """Cut only the event windows (all years in one Harmony job), average each window per pixel, then over the box.

    Returns {year: (value, valid_fraction)}.
    """
    import earthaccess
    import xarray as xr
    from harmony import BBox as HBBox, Client, Collection, Request

    from .core import _box_mean, _concept_id, _job_id, _open_var, _standardize, _wait

    say = progress or print
    cache.mkdir(parents=True, exist_ok=True)
    done = cache / ".complete"
    if not done.exists():
        ids = []
        for c in centers:
            g = earthaccess.search_data(short_name=src["short_name"], version=src["version"], bounding_box=bbox.tuple(),
                                        temporal=(str((c - timedelta(days=window_days)).date()),
                                                  str((c + timedelta(days=window_days)).date())))
            ids += [x["meta"]["concept-id"] for x in g]
        if not ids:
            return {}
        say(f"  cutting {len(ids)} daily files to the box ({len(centers)} years); first time takes ~10 min, then cached")
        client = Client()
        req = Request(collection=Collection(id=_concept_id(src)), spatial=HBBox(*bbox.tuple()), granule_id=ids,
                      variables=[src["harmony_variable"]])
        job = _job_id(client.submit(req))
        _wait(client, job, "cutting files to your box")
        say("  downloading the cut files")
        for f in client.download_all(job, directory=str(cache), overwrite=False):
            f.result()
        done.touch()
    by_year: dict[int, list] = {}
    for path in sorted(cache.glob("*.nc4")):
        da = _standardize(_open_var(path, src["variable"]))
        t = pd.Timestamp(da.time.values[0])
        for c in centers:
            if abs((t - c).days) <= window_days:
                by_year.setdefault(c.year, []).append(da)
    out = {}
    for y, das in by_year.items():
        if len(das) < max(3, window_days // 2):
            continue
        m = xr.concat(das, "time").mean("time", skipna=True)
        bm = _box_mean(m.expand_dims(time=[pd.Timestamp(f"{y}-01-01")]), bbox)
        out[y] = (float(bm["value"].iloc[0]), float(bm["valid_fraction"].iloc[0]))
    return out


def event_impact(bbox: BBox, vid: str, event_date: str, window_days: int = 7,
                 baseline_years: int = 15, progress=None) -> dict:
    """Event window vs the same calendar window in each earlier year.

    Uses the variable's near-real-time twin (event_twin in sources.yaml) when there is one, so recent events
    have data. Daily data: mean over event_date +/- window_days. Monthly data: the event's month.
    """
    cat = load_catalog()
    vid = cat[vid].get("event_twin", vid)
    src = cat[vid]
    ev = pd.Timestamp(event_date)
    years = list(range(ev.year - baseline_years, ev.year + 1))
    per_year, valid = {}, {}
    if src["method"] == "windows":
        login()
        centers = []
        for y in years:
            try:
                centers.append(ev.replace(year=y))
            except ValueError:  # 29 Feb
                centers.append(ev.replace(year=y, day=28))
        key = f"{bbox.key()}_win_{ev:%Y%m%d}_{window_days}_{baseline_years}"
        vals = _window_values(src, bbox, centers, window_days, DATA / "raw" / vid / key, progress)
        for y, (v, f) in vals.items():
            if f >= 0.5:  # at least half the box seen during the window
                per_year[y], valid[y] = v, f
        units = src.get("units", "")
        series = pd.Series(per_year).sort_index()
        window = f"{(ev - timedelta(days=window_days)).date()} to {(ev + timedelta(days=window_days)).date()}"
    elif src["cadence"] == "daily" and src["method"] == "giovanni":
        login()
        s0, s1 = _clip_dates(src, f"{years[0]}-01-01", f"{ev.year}-12-31")
        df, units = _fetch_giovanni(src, bbox, s0, s1, _raw_dir(vid, bbox, s0, s1), monthly=False)
        series = df["value"].dropna()
        for y in years:
            c = ev.replace(year=y)
            win = series[(series.index >= c - timedelta(days=window_days)) & (series.index <= c + timedelta(days=window_days))]
            if len(win) >= max(3, window_days // 2):
                per_year[y] = float(win.mean())
        window = f"{(ev - timedelta(days=window_days)).date()} to {(ev + timedelta(days=window_days)).date()}"
    else:
        wide, rep = pull(bbox, f"{years[0]}-01-01", f"{ev.year}-12-31", [vid], progress=progress)
        units = (rep.get("units", pd.Series([""])).iloc[0]) or src.get("units", "")
        if vid not in wide:
            return {"id": vid, "name": src["name"], "source": src["instrument"], "verdict": str(rep.iloc[0].get("status"))}
        series = wide[vid].dropna()
        per_year = {p.year: float(v) for p, v in series.items() if p.month == ev.month}
        window = ev.strftime("%B") + " (monthly data)"
    this = per_year.pop(ev.year, None)
    base = np.array(list(per_year.values()))
    out = {"id": vid, "name": src["name"], "source": src["instrument"], "units": units, "window": window,
           "event_value": this, "baseline_years": sorted(per_year), "baseline_values": base.tolist(),
           "series": series, "per_year": {**per_year, **({ev.year: this} if this is not None else {})}}
    if this is None:
        latest = series.index.max() if len(series) else None
        out["verdict"] = f"No data for this window yet (latest available: {latest})"
        return out
    mu = float(base.mean()) if base.size else np.nan
    sd = float(base.std(ddof=1)) if base.size > 1 else np.nan
    z = (this - mu) / sd if np.isfinite(sd) and sd > 0 else np.nan
    out.update(baseline_mean=mu, z=z, change_pct=(100 * (this - mu) / abs(mu)) if mu else np.nan,
               verdict=verdict(z, int((base < this).sum()), int(base.size)))
    return out


def longterm(bbox: BBox, vid: str, start: str = "2003-01-01", end: str | None = None) -> dict:
    """Trend over the record, for slow changes (mining, drought, glaciers). Same method as earthpull.trends."""
    from .trends import analyze

    end = end or f"{datetime.now().year}-12-31"
    wide, rep = pull(bbox, start, end, [vid])
    src = load_catalog()[vid]
    if vid not in wide:
        return {"id": vid, "error": str(rep.iloc[0].get("status"))}
    s = wide[vid].dropna()
    units = (rep.get("units", pd.Series([""])).iloc[0]) or src.get("units", "")
    out = {"id": vid, "name": src["name"], "source": src["instrument"], "units": units, "series": s,
           "months": int(len(s))}
    r = analyze(wide[[vid]], {vid: units}, {vid: tuple(src.get("breaks", ()))}).iloc[0]
    out["verdict"] = r["verdict"]
    if pd.notna(r.get("slope_per_decade")):
        out.update(slope_per_decade=float(r["slope_per_decade"]), p=float(r["p_ar1"]),
                   ci_low=float(r["ci_low"]), ci_high=float(r["ci_high"]))
    return out
    t = np.array([(p.year - s.index[0].year) * 12 + p.month - s.index[0].month for p in s.index], float)
    r = mk.hamed_rao_modification_test(anom.values)
    slope = stats.theilslopes(anom.values, t)[0] * 120
    out.update(slope_per_decade=slope, p=float(r.p),
               verdict=("Clear rise" if slope > 0 else "Clear fall") if r.p < 0.05 else "No clear change yet")
    return out


# ------------------------------------------------------------------ 5. latest environment news feed

KIND_RANK = {"city": 0, "state": 1, "country": 2}


def latest_environment_news(days: int = 7, per_topic: int = 60) -> pd.DataFrame:
    """One Google News query per topic in topics.yaml, each headline tied to the most specific place it names.

    Only headlines with a recognised place are kept, so every row can be checked on the map.
    """
    import time

    tps = topics()
    rows = []
    for tid, tp in tps.items():
        q = " OR ".join(f'"{k}"' if " " in k else k for k in tp["keywords"][:8])
        try:
            df = search_news(q, days)
        except Exception:
            continue
        df = filter_headlines(df, tid).head(per_topic)
        for r in df.itertuples():
            if tid not in match_topics(r.title):
                continue
            if tp.get("mode") == "event" and OLD_YEAR.search(r.title):
                continue  # "Volcano - Pinatubo, 1991": a past event, not news
            pl = find_places([r.title])
            if pl.empty:
                continue
            pl = pl.assign(k=pl.kind.map(KIND_RANK)).sort_values(["k", "mentions"]).iloc[0]
            rows.append({"date": r.date, "time": getattr(r, "time", None), "topic": tid, "topic_label": tp["label"], "title": r.title,
                         "source": r.source, "place": pl["name"], "kind": pl["kind"],
                         "west": pl.west, "south": pl.south, "east": pl.east, "north": pl.north, "link": r.link})
        time.sleep(0.5)  # be polite to the feed
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.drop_duplicates("title").sort_values(["date", "time"], ascending=False, ignore_index=True)
    # Keep the list varied: at most MAX_PER_PLACE stories per place and MAX_PER_TOPIC per topic (newest first),
    # then interleave topics so one busy topic (say, a week of floods) cannot fill the panel.
    out = out[out.groupby("place").cumcount() < MAX_PER_PLACE]
    out = out[out.groupby("topic").cumcount() < MAX_PER_TOPIC]
    out = out.assign(_r=out.groupby("topic").cumcount()).sort_values(["_r", "date"], ascending=[True, False])
    return out.drop(columns="_r").reset_index(drop=True)


MAX_PER_TOPIC = 6
OLD_YEAR = re.compile(r"\b(1[6-9]\d\d|20[01]\d|202[0-3])\b")
MAX_PER_PLACE = 2
