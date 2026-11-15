"""Bounding box in, one tidy monthly table out.

check()  - which variables have data for this box and time range (metadata only, no download)
pull()   - fetch each variable for the box, area-average it, merge into one table
inspect()- open one real granule and list its variables (to confirm names in sources.yaml)
"""
from __future__ import annotations

import hashlib
import re
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import yaml

import os

os.environ.setdefault("NUM_REQUESTS_WORKERS", "16")  # Harmony downloads in parallel (library default is 3)

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("EARTHPULL_DATA", ROOT / "data"))  # on Cloud Run: a mounted GCS bucket
CATALOG = Path(__file__).with_name("sources.yaml")

warnings.filterwarnings("ignore", category=FutureWarning)


# ---------------------------------------------------------------- basics

@dataclass(frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    @classmethod
    def parse(cls, text: str) -> "BBox":
        w, s, e, n = (float(x) for x in text.split(","))
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
            raise ValueError("bbox must be west,south,east,north with west<east, south<north")
        return cls(w, s, e, n)

    def tuple(self):
        return (self.west, self.south, self.east, self.north)

    def key(self) -> str:
        return hashlib.md5(",".join(f"{v:.4f}" for v in self.tuple()).encode()).hexdigest()[:10]


def load_catalog() -> dict:
    return yaml.safe_load(CATALOG.read_text())


def login():
    """Earthdata Login. Same account as Giovanni. Saves ~/.netrc so Harmony works too."""
    import earthaccess

    netrc = Path.home() / ".netrc"
    if _env_creds() and not netrc.exists():  # containers: secrets arrive as env vars; Harmony reads ~/.netrc
        netrc.write_text(f"machine urs.earthdata.nasa.gov login {os.environ['EARTHDATA_USERNAME']} "
                         f"password {os.environ['EARTHDATA_PASSWORD']}\n")
        netrc.chmod(0o600)
    auth = earthaccess.login(strategy="environment") if _env_creds() else None
    if not auth or not auth.authenticated:
        auth = earthaccess.login(strategy="netrc") if (Path.home() / ".netrc").exists() else None
    if not auth or not auth.authenticated:
        auth = earthaccess.login(strategy="interactive", persist=True)
    if not auth.authenticated:
        raise SystemExit("Earthdata login failed.")
    return auth


def _env_creds() -> bool:
    import os
    return bool(os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD"))


def _collection(src: dict) -> dict:
    import earthaccess

    kw = {"short_name": src["short_name"]}
    if src.get("version"):
        kw["version"] = src["version"]
    found = earthaccess.search_datasets(**kw)
    if not found:
        raise LookupError(f"{src['short_name']} v{src.get('version')} not found in CMR")
    return found[0]


def _clip_dates(src: dict, start: str, end: str) -> tuple[str, str]:
    """Clip the request to the product's own record (Giovanni rejects dates outside it)."""
    rng = _collection(src)["umm"].get("TemporalExtents", [{}])[0].get("RangeDateTimes", [{}])[0]
    b, e = rng.get("BeginningDateTime", "")[:10], (rng.get("EndingDateTime") or "")[:10]
    if b and start < b:
        start = f"{b[:7]}-01" if b[8:10] == "01" else b
        if b[8:10] != "01":  # start on the first full month
            start = str((pd.Period(b[:7], "M") + 1).to_timestamp().date())
    if e and end > e:
        end = e
    return start, end


def _concept_id(src: dict) -> str:
    import earthaccess

    kw = {"short_name": src["short_name"]}
    if src.get("version"):
        kw["version"] = src["version"]
    found = earthaccess.search_datasets(**kw)
    if not found:
        raise LookupError(f"{src['short_name']} v{src.get('version')} not found in CMR")
    return found[0]["meta"]["concept-id"]


# ---------------------------------------------------------------- check

def check(bbox: BBox, start: str, end: str, ids: list[str] | None = None) -> pd.DataFrame:
    """Granule counts per variable for the box and dates. Metadata only, no login needed."""
    import earthaccess

    cat = load_catalog()
    rows = []
    months = len(pd.period_range(start, end, freq="M"))
    for vid, src in cat.items():
        if (ids and vid not in ids) or (not ids and src.get("event_only")):
            continue
        row = {"id": vid, "name": src["name"], "source": src["instrument"],
               "cadence": src["cadence"], "domain": src["domain"], "method": src["method"]}
        try:
            q = earthaccess.DataGranules().concept_id(_concept_id(src))
            q = q.bounding_box(*bbox.tuple()).temporal(start, end)
            hits = q.hits()
            row["granules"] = hits
            if "GRAC" in src["short_name"]:
                row["coverage"] = "single file, whole record"
            elif src["cadence"] == "monthly":
                row["coverage"] = f"{min(hits, months)}/{months} months"
            else:
                row["coverage"] = f"{hits} daily files"
            row["available"] = hits > 0
        except Exception as exc:  # network or CMR error: report, keep going
            row.update(granules=None, available=False, coverage=f"error: {exc}")
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- fetch

def _raw_dir(vid: str, bbox: BBox, start: str, end: str) -> Path:
    d = DATA / "raw" / vid / f"{bbox.key()}_{start}_{end}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _job_id(job) -> str:
    """Harmony returns an id string, or the whole job dict when it reuses an identical finished job."""
    if isinstance(job, str):
        return job
    if job.get("jobID"):
        return job["jobID"]
    m = re.search(r"/(?:stac|jobs)/([0-9a-f-]{36})", str(job))
    if not m:
        raise ValueError(f"cannot find a job id in Harmony response: {str(job)[:200]}")
    return m.group(1)


_PROGRESS = None  # optional callback(str) set by pull(); the UI uses it to show live status


def _say(msg: str) -> None:
    print(msg)
    if _PROGRESS:
        _PROGRESS(msg)


def _wait(client, job: str, label: str) -> None:
    """Poll a Harmony job, resuming it if Harmony pauses it, and report progress."""
    import time

    last = None
    while True:
        s = client.status(job)
        state, pct = s["status"], s.get("progress", 0)
        if (state, pct) != last:
            _say(f"  {label}: NASA is processing ({pct}%)")
            last = (state, pct)
        if state == "paused":  # Harmony pauses big jobs after the first page
            client.resume(job)
        elif state in ("successful", "complete_with_errors"):
            return
        elif state in ("failed", "canceled"):
            raise RuntimeError(f"{label} job {state}: {s.get('message', '')}")
        time.sleep(4)


def _fetch_harmony(src: dict, bbox: BBox, start: str, end: str, out: Path) -> list[Path]:
    from harmony import BBox as HBBox, Client, Collection, Request

    done = out / ".complete"
    if done.exists():  # only reuse a cache that finished downloading
        return sorted(p for p in out.iterdir() if p.suffix in (".nc", ".nc4", ".h5", ".hdf"))
    client = Client()  # reads ~/.netrc written by login()
    whole_globe = bbox.west <= -180 and bbox.east >= 180 and bbox.south <= -90 and bbox.north >= 90
    req = Request(
        collection=Collection(id=_concept_id(src)),
        # A -180..180 box makes Harmony return a single longitude column, so ask for no spatial cut at all.
        spatial=None if whole_globe else HBBox(*bbox.tuple()),
        temporal={"start": datetime.fromisoformat(start), "stop": datetime.fromisoformat(end)},
        variables=[src.get("harmony_variable", src["variable"])],
    )
    if not req.is_valid():
        raise ValueError(f"Harmony request invalid: {req.error_messages()}")
    job = _job_id(client.submit(req))
    print(f"  harmony job {job}")
    _wait(client, job, "cutting files to your box")
    _say("  downloading the cut files")
    paths = sorted(Path(f.result()) for f in client.download_all(job, directory=str(out), overwrite=False))
    done.touch()
    return paths


def _fetch_giovanni(src: dict, bbox: BBox, start: str, end: str, out: Path,
                    monthly: bool = True) -> tuple[pd.DataFrame, str]:
    """Giovanni's own area-average engine via Harmony. One small CSV for the whole period."""
    from harmony import BBox as HBBox, Client, Collection, Request

    csvs = sorted(out.glob("GIOVANNI-areaAvgTimeSeries*.csv"))
    if not csvs:
        client = Client()
        req = Request(
            collection=Collection(id=_concept_id(src)),
            spatial=HBBox(*bbox.tuple()),
            temporal={"start": datetime.fromisoformat(start), "stop": datetime.fromisoformat(end)},
            variables=[src["giovanni_id"]], average="area", format="text/csv",
        )
        job = _job_id(client.submit(req))
        print(f"  giovanni job {job}")
        _wait(client, job, "Giovanni averaging")
        csvs = [Path(f.result()) for f in client.download_all(job, directory=str(out), overwrite=True)]
    lines = csvs[0].read_text().splitlines()
    header = next(i for i, l in enumerate(lines) if l.startswith("time,"))
    fill = next((float(l.split(",")[1]) for l in lines[:header] if l.startswith("Fill Value")), None)
    raw = pd.read_csv(csvs[0], skiprows=header)
    val = raw.iloc[:, 1].astype(float)
    if fill is not None:
        val[np.isclose(val, fill)] = np.nan
    df = pd.DataFrame({"value": val.values, "valid_fraction": np.nan}, index=pd.to_datetime(raw["time"], format="ISO8601"))
    if not monthly:  # keep native time steps (daily for OMI) for short-event analysis
        df.index.name = "time"
        return df, src.get("units", "")
    df = df.groupby(df.index.to_period("M")).mean()  # daily (OMI) -> monthly
    df.index.name = "month"
    return df, src.get("units", "")


def _fetch_download(src: dict, bbox: BBox, start: str, end: str, out: Path) -> list[Path]:
    import earthaccess

    kw = {"short_name": src["short_name"], "bounding_box": bbox.tuple()}
    if src.get("version"):
        kw["version"] = src["version"]
    if "GRAC" not in src["short_name"]:  # GRACE is one file spanning everything
        kw["temporal"] = (start, end)
    granules = earthaccess.search_data(**kw)
    _say(f"  downloading {len(granules)} global file(s); reused for every later box")
    shared = DATA / "raw" / "_global" / src["short_name"]  # whole-globe files reused for every bbox
    shared.mkdir(parents=True, exist_ok=True)
    return sorted(Path(p) for p in earthaccess.download(granules, local_path=str(shared)))


# ---------------------------------------------------------------- open + reduce

def _open_var(path: Path, var: str, mask_var: str | None = None) -> xr.DataArray:
    """Open one variable from netCDF/HDF5 (any group) or HDF4.
    mask_var: a 0/1 variable in the same file (e.g. GRACE land_mask); cells where it is 0 become NaN."""
    if path.suffix.lower() == ".hdf":
        return _open_hdf4(path, var)
    ds = xr.open_dataset(path)
    if var in ds:
        da = ds[var]
        if mask_var and mask_var in ds:
            da = da.where(ds[mask_var] > 0)
        return _ensure_time(da, path)
    import netCDF4

    with netCDF4.Dataset(path) as nc:  # data inside groups (IMERG /Grid, AIRS, OMI HDF-EOS)
        stack = [nc]
        while stack:
            grp = stack.pop()
            for sub in grp.groups.values():
                if var in sub.variables:
                    return _ensure_time(_nc_group_var(sub, var), path)
                stack.append(sub)
    raise KeyError(f"{var} not in {path.name}; run `python -m earthpull inspect` to list names")


def _nc_group_var(grp, var: str) -> xr.DataArray:
    """Read a grouped variable; coordinates may live in the same group or any parent group."""
    import netCDF4

    v = grp.variables[var]
    data = np.ma.filled(v[:].astype("float64"), np.nan)
    coords = {}
    for d in v.dimensions:
        g = grp
        while g is not None and d not in g.variables:
            g = g.parent
        if g is None:
            continue
        cv = g.variables[d]
        vals = cv[:]
        if d.lower().startswith("time") and hasattr(cv, "units"):
            vals = netCDF4.num2date(vals, cv.units, getattr(cv, "calendar", "standard"))
            vals = pd.to_datetime([f"{t.year:04d}-{t.month:02d}-{t.day:02d}" for t in vals])
        coords[d] = np.asarray(vals)
    return xr.DataArray(data, dims=v.dimensions, coords=coords, name=var,
                        attrs={"units": getattr(v, "units", "")})


_DATE_PATTERNS = [
    (r"AIRS\.(\d{4})\.(\d{2})\.(\d{2})", lambda m: f"{m[1]}-{m[2]}-{m[3]}"),         # AIRS.2020.01.01
    (r"_(\d{4})m(\d{2})(\d{2})_", lambda m: f"{m[1]}-{m[2]}-{m[3]}"),                 # OMI 2020m0101
    (r"\.A(\d{4})(\d{3})\.", lambda m: str(datetime.strptime(m[1] + m[2], "%Y%j").date())),  # MODIS A2020001
    (r"(\d{4})(\d{2})(\d{2})-S\d{6}", lambda m: f"{m[1]}-{m[2]}-{m[3]}"),             # IMERG
]


def _ensure_time(da: xr.DataArray, path: Path) -> xr.DataArray:
    if any(d.lower().startswith("time") for d in da.dims):
        return da.rename({d: "time" for d in da.dims if d.lower().startswith("time")})
    for pat, fmt in _DATE_PATTERNS:
        m = re.search(pat, path.name)
        if m:
            return da.expand_dims(time=[pd.Timestamp(fmt(m))])
    raise ValueError(f"{path.name}: no time dimension and no date in the filename")


def _open_hdf4(path: Path, var: str) -> xr.DataArray:
    """MODIS CMG (0.05 deg global). Applies fill, valid range and scale from file attributes."""
    from pyhdf.SD import SD, SDC

    sd = SD(str(path), SDC.READ)
    sds = sd.select(var)
    raw = sds.get().astype("float64")
    a = sds.attributes()
    fill = a.get("_FillValue")
    if fill is not None:
        raw[raw == fill] = np.nan
    if "valid_range" in a:
        lo, hi = a["valid_range"]
        raw[(raw < lo) | (raw > hi)] = np.nan
    scale, offset = float(a.get("scale_factor", 1.0)), float(a.get("add_offset", 0.0))
    # MOD13 stores scale_factor=10000 meaning "divide by"; MOD11 stores 0.02 meaning "multiply by".
    val = (raw - offset) / scale if scale > 1 else (raw - offset) * scale
    ny, nx = val.shape
    lat = 90 - (np.arange(ny) + 0.5) * 180 / ny
    lon = -180 + (np.arange(nx) + 0.5) * 360 / nx
    m = re.search(r"\.A(\d{4})(\d{3})\.", path.name)
    t = pd.Timestamp(datetime.strptime(m.group(1) + m.group(2), "%Y%j"))
    da = xr.DataArray(val[None], dims=("time", "lat", "lon"),
                      coords={"time": [t], "lat": lat, "lon": lon}, name=var,
                      attrs={"units": a.get("units", "")})
    sd.end()
    return da


def _standardize(da: xr.DataArray) -> xr.DataArray:
    ren = {}
    for d in da.dims:
        dl = d.lower()
        if dl in ("latitude", "y") or dl.startswith(("lat", "ydim")):
            ren[d] = "lat"
        elif dl in ("longitude", "x") or dl.startswith(("lon", "xdim")):
            ren[d] = "lon"
    da = da.rename(ren)
    if "lon" in da.coords and float(da.lon.max()) > 180:  # 0..360 grids (GRACE) -> -180..180
        da = da.assign_coords(lon=((da.lon + 180) % 360) - 180).sortby("lon")
    return da.sortby("lat")


_WEIGHT_CACHE: dict = {}


def _shape_weights(da: xr.DataArray, shape) -> xr.DataArray:
    """Share of each grid cell inside the outline (0..1), like Giovanni's shape masks.
    Cached per (outline, grid): a pull averages hundreds of monthly files on the same grid."""
    key = (hashlib.md5(shape.wkb).hexdigest(), hashlib.md5(np.asarray(da.lat.values, float).tobytes()).hexdigest(),
           hashlib.md5(np.asarray(da.lon.values, float).tobytes()).hexdigest())
    if key in _WEIGHT_CACHE:
        return _WEIGHT_CACHE[key]
    w = _shape_weights_uncached(da, shape)
    _WEIGHT_CACHE[key] = w
    return w


def _regular(v: np.ndarray) -> np.ndarray:
    """Snap nearly-regular coordinates (float32 noise, e.g. IMERG) to an exactly regular grid for regionmask."""
    v = np.asarray(v, float)
    if len(v) < 3:
        return v
    d = (v[-1] - v[0]) / (len(v) - 1)
    reg = v[0] + d * np.arange(len(v))
    return reg if np.max(np.abs(reg - v)) < 1e-3 * abs(d) else v


def _shape_weights_uncached(da: xr.DataArray, shape) -> xr.DataArray:
    import regionmask

    lat0, lon0 = da.lat.values, da.lon.values
    da = da.assign_coords(lat=_regular(lat0), lon=_regular(lon0))

    frac = regionmask.Regions([shape]).mask_3D_frac_approx(da.lon, da.lat).isel(region=0, drop=True)
    frac = frac.fillna(0)
    if float(frac.sum()) == 0:  # outline smaller than one cell: use the cell holding its centre
        c = shape.representative_point()
        frac = xr.zeros_like(frac)
        frac.loc[dict(lat=da.lat.sel(lat=c.y, method="nearest"), lon=da.lon.sel(lon=c.x, method="nearest"))] = 1.0
    return frac.assign_coords(lat=lat0, lon=lon0)  # back to the data's own coordinates so they align exactly


def _box_mean(da: xr.DataArray, bbox: BBox, shape=None) -> pd.DataFrame:
    """cos(lat)-weighted mean over the box (or over an outline, weighting each cell by its share inside it),
    plus the fraction of the region's area with valid data."""
    da = _standardize(da)
    pad = 0.0
    if shape is not None and da.sizes.get("lat", 0) > 1:  # include edge cells that the outline only partly covers
        pad = float(max(abs(np.diff(da.lat.values[:2])[0]), abs(np.diff(da.lon.values[:2])[0])))
    da = da.sel(lat=slice(bbox.south - pad, bbox.north + pad), lon=slice(bbox.west - pad, bbox.east + pad))
    if da.sizes.get("lat", 0) == 0 or da.sizes.get("lon", 0) == 0:
        raise ValueError("box is smaller than one grid cell of this product; make it larger")
    extra = [d for d in da.dims if d not in ("time", "lat", "lon")]
    if extra:  # e.g. a singleton level/band dim
        da = da.isel({d: 0 for d in extra})
    w = np.cos(np.deg2rad(da.lat)).broadcast_like(da)
    if shape is not None:
        w = w * _shape_weights(da, shape).broadcast_like(da)
    valid = da.notnull()
    mean = (da * w).sum(("lat", "lon")) / w.where(valid).sum(("lat", "lon"))
    frac = w.where(valid).sum(("lat", "lon")) / w.sum(("lat", "lon"))
    tv = da.time.values
    try:
        idx = pd.to_datetime(tv)
    except TypeError:  # cftime dates (IMERG uses a Julian calendar)
        idx = pd.to_datetime([f"{t.year:04d}-{t.month:02d}-{t.day:02d}" for t in tv])
    df = pd.DataFrame({"value": mean.values, "valid_fraction": frac.values}, index=idx)
    df.attrs["cells"] = int(da.sizes["lat"] * da.sizes["lon"]) if shape is None else float(
        (w.isel(time=0) / np.cos(np.deg2rad(da.lat))).sum()) if "time" in w.dims else 0.0
    return df


def _reduce(paths: list[Path], var: str, bbox: BBox, daily: bool = False, shape=None,
            mask_var: str | None = None) -> tuple[pd.DataFrame, str]:
    parts, units = [], ""
    if daily:  # average each pixel over the month first: one day's swath covers only part of the box
        by_month: dict = {}
        for p in paths:
            da = _standardize(_open_var(p, var, mask_var))
            units = units or str(da.attrs.get("units", ""))
            by_month.setdefault(pd.Timestamp(da.time.values[0]).to_period("M"), []).append(da)
        for month, das in sorted(by_month.items()):
            m = xr.concat(das, "time").mean("time", skipna=True)
            parts.append(_box_mean(m.expand_dims(time=[month.to_timestamp()]), bbox, shape))
    else:
        for p in paths:
            da = _open_var(p, var, mask_var)
            units = units or str(da.attrs.get("units", ""))
            parts.append(_box_mean(da, bbox, shape))
    df = pd.concat(parts).sort_index()
    df = df.groupby(df.index.to_period("M")).mean()  # daily -> monthly, and dedupe
    df.index.name = "month"
    return df, units


def _from_cube(cube: Path, src: dict, bbox: BBox, start: str, end: str, shape=None):
    """Slice a pre-built global cube (see earthpull.cubes). Seconds instead of a NASA job."""
    with xr.open_dataset(cube) as ds:
        da = ds[src["variable"]].sel(time=slice(start, end)).load()
    if da.sizes.get("time", 0) == 0:
        return None, ""
    df = _box_mean(da, bbox, shape)
    df = df.groupby(df.index.to_period("M")).mean()
    df.index.name = "month"
    _say(f"  from the local global cube ({len(df)} months)")
    return df, str(da.attrs.get("units", src.get("units", "")))


def bbox_of(shape, pad: float = 0.0) -> BBox:
    w, s_, e, n = shape.bounds
    return BBox(max(w - pad, -180), max(s_ - pad, -90), min(e + pad, 180), min(n + pad, 90))


def pull(bbox: BBox | None, start: str, end: str, ids: list[str] | None = None,
         include_daily: bool = False, min_valid: float = 0.7,
         progress=None, shape=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (wide table: month x variable, report: one row per variable).

    shape: optional outline (shapely geometry, lon/lat). Values are then averaged over the outline, each grid cell
    weighted by its share inside it. Giovanni's averaging only takes rectangles, so with an outline the data are cut
    to the outline's box by Harmony and the outline is applied locally (slower the first time, then cached)."""
    global _PROGRESS
    _PROGRESS = progress
    if shape is not None and bbox is None:
        bbox = bbox_of(shape)
    login()
    cat = load_catalog()
    series, report = {}, []
    for vid, src in cat.items():
        if (ids and vid not in ids) or (not ids and src.get("event_only")) or src["method"] == "windows":
            continue
        if src["cadence"] == "daily" and not include_daily and src["method"] != "giovanni":
            report.append({"id": vid, "status": "skipped (daily; pass --include-daily)"})
            continue
        _say(f"[{vid}] {src['name']} via {src['method']}")
        try:
            start_v, end_v = _clip_dates(src, start, end)
            if start_v >= end_v:
                raise ValueError(f"no overlap: product covers from {start_v}")
            raw_dir = _raw_dir(vid, bbox, start_v, end_v)
            df = None
            cube = DATA / "cubes" / f"{vid}.nc"
            fetch_box = bbox_of(shape, 1.0) if shape is not None else bbox  # padded so edge cells are included
            if shape is not None:
                raw_dir = _raw_dir(vid, fetch_box, start_v, end_v)
            region_kind = "outline" if shape is not None else "box"
            if cube.exists():
                df, units = _from_cube(cube, src, bbox, start_v, end_v, shape)
                method = "local cube"
                if df is not None and len(df) == 0:
                    df = None
            use_giovanni = src["method"] == "giovanni" and (shape is None or src["cadence"] == "daily")
            if shape is not None and src["method"] == "giovanni" and src["cadence"] == "daily":
                region_kind = "box (outline not applied: daily product)"
            if df is None and use_giovanni:
                try:
                    df, units = _fetch_giovanni(src, bbox, start_v, end_v, raw_dir)
                    method = "giovanni"
                except Exception as exc:
                    _say(f"  Giovanni could not do this one; cutting files instead ({exc})")
            if df is None:
                fetch = _fetch_download if src["method"] == "download" else _fetch_harmony
                method = "download" if src["method"] == "download" else "harmony"
                h = dict(src)
                h.setdefault("harmony_variable", src["variable"])
                paths = fetch(h, fetch_box, start_v, end_v, raw_dir)
                df, units = _reduce(paths, src["variable"], bbox, src["cadence"] == "daily",
                                    shape if "outline" == region_kind else None, src.get("mask_var"))
            units = units or src.get("units", "")
            df = df.loc[pd.Period(start, "M"):pd.Period(end, "M")]
            df.loc[df["valid_fraction"] < min_valid, "value"] = np.nan  # NaN fraction (giovanni) is kept
            series[vid] = df["value"]
            report.append({"id": vid, "status": "ok", "via": method, "region": region_kind, "units": units,
                           "months": int(df["value"].notna().sum()),
                           "first": str(df["value"].first_valid_index()),
                           "last": str(df["value"].last_valid_index()),
                           "mean_valid_fraction": (round(float(df["valid_fraction"].mean()), 2)
                                                   if df["valid_fraction"].notna().any() else None)})
        except Exception as exc:
            _say(f"  failed: {exc}")
            report.append({"id": vid, "status": f"failed: {exc}"})
    wide = pd.DataFrame(series)
    wide.index.name = "month"
    return wide, pd.DataFrame(report)


def inspect(vid: str) -> None:
    """Download one granule and print every variable with dims and units."""
    import earthaccess

    login()
    src = load_catalog()[vid]
    kw = {"short_name": src["short_name"], "count": 1}
    if src.get("version"):
        kw["version"] = src["version"]
    g = earthaccess.search_data(**kw)
    p = Path(earthaccess.download(g[:1], local_path=str(DATA / "raw" / "_inspect"))[0])
    print(p.name)
    if p.suffix.lower() == ".hdf":
        from pyhdf.SD import SD, SDC
        for name, info in SD(str(p), SDC.READ).datasets().items():
            print(f"  {name}  dims={info[0]}")
        return
    import netCDF4

    def walk(g, prefix=""):
        for n, v in g.variables.items():
            print(f"  {prefix}/{n}  dims={v.dimensions}  units={getattr(v, 'units', '')}")
        for n, s in g.groups.items():
            walk(s, f"{prefix}/{n}")
    with netCDF4.Dataset(p) as nc:
        walk(nc)


def export_csv(wide: pd.DataFrame, report: pd.DataFrame, region: str, start: str, end: str) -> str:
    """CSV text whose header says, for every column, the dataset, version, variable, units and how the region
    was averaged, so anyone can check the numbers against NASA's own tools."""
    cat = load_catalog()
    rep = report.set_index("id") if "id" in report else pd.DataFrame()
    lines = [f"# earthpull export | region: {region} | period: {start} to {end}",
             "# values are monthly means over the region, weighted by cos(latitude) (and by each cell's share "
             "inside the outline when an outline was used)"]
    cols = {}
    for vid in wide.columns:
        src = cat.get(vid, {})
        r = rep.loc[vid] if vid in rep.index else {}
        units = (r.get("units") if hasattr(r, "get") else None) or src.get("units", "")
        cols[vid] = f"{vid} [{units}]" if units else vid
        lines.append(f"# {cols[vid]}: {src.get('name', vid)} | {src.get('instrument', '')} | "
                     f"{src.get('short_name', '')} v{src.get('version') or '-'} variable {src.get('variable', '')} | "
                     f"fetched via {r.get('via', '?') if hasattr(r, 'get') else '?'}, "
                     f"region {r.get('region', 'box') if hasattr(r, 'get') else 'box'}")
    out = wide.rename(columns=cols)
    out.index = out.index.astype(str)
    return "\n".join(lines) + "\n" + out.to_csv()
