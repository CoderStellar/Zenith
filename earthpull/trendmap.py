"""Global per-pixel trend maps: where is each variable rising, falling, or not clearly changing?

For every grid cell: trend fitted jointly with annual + semiannual harmonics on the real monthly grid, with an
AR(1)-adjusted (effective sample size) p-value, the same primary method as earthpull.trends and IPCC AR6.
Then Benjamini-Hochberg across all cells (Wilks 2016): alpha_FDR 0.10 for smooth fields, 0.05 for precipitation.
Fully vectorised: cells that share the same missing months are fitted in one batch.

  python -m earthpull.trendmap --var air_temp --start 2003-01-01 --end 2024-12-31 --res 0.5
  python -m earthpull.trendmap --var all ...

Writes data/trendmaps/<var>_<start>_<end>.nc and .png. Heavy: built to run on a cloud VM.
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
import xarray as xr

from .core import (DATA, BBox, _clip_dates, _fetch_download, _fetch_harmony, _open_var, _raw_dir,
                   _standardize, load_catalog, login)

GLOBE = BBox(-180, -90, 180, 90)
MIN_MONTHS = 120  # 10 years of valid data per cell, else "too short to tell"


# ------------------------------------------------------------- build the cube

def _coarsen(da: xr.DataArray, res: float) -> xr.DataArray:
    dy = float(abs(np.diff(da.lat.values[:2])[0]))
    dx = float(abs(np.diff(da.lon.values[:2])[0]))
    ky, kx = max(1, round(res / dy)), max(1, round(res / dx))
    if ky == 1 and kx == 1:
        return da
    return da.coarsen(lat=ky, lon=kx, boundary="trim").mean()


def build_cube(vid: str, start: str, end: str, res: float) -> tuple[xr.DataArray, str]:
    src = load_catalog()[vid]
    start, end = _clip_dates(src, start, end)
    raw = _raw_dir(vid, GLOBE, start, end)
    if src["method"] == "download":
        paths = _fetch_download(src, GLOBE, start, end, raw)
    else:  # giovanni-method sources still need the full grid here, so subset via Harmony
        h = dict(src)
        h.setdefault("harmony_variable", src["variable"])
        paths = _fetch_harmony(h, GLOBE, start, end, raw)
    months: dict = {}
    units = src.get("units", "")
    for p in paths:
        da = _standardize(_open_var(p, src["variable"], src.get("mask_var")))
        units = units or str(da.attrs.get("units", ""))
        da = _coarsen(da, res)
        if "time" in da.dims:
            for t in range(da.sizes["time"]):
                one = da.isel(time=t)
                m = pd.Timestamp(da.time.values[t]).to_period("M")
                months.setdefault(m, []).append(one.drop_vars("time", errors="ignore"))
    lo, hi = pd.Period(start, "M"), pd.Period(end, "M")
    keys = sorted(k for k in months if lo <= k <= hi)
    frames = [xr.concat(months[k], "t").mean("t", skipna=True) if len(months[k]) > 1 else months[k][0]
              for k in keys]  # daily -> monthly
    cube = xr.concat(frames, "time").assign_coords(time=[k.to_timestamp() for k in keys])
    return cube.astype("float32"), units


# ------------------------------------------------------------- per-cell tests

ALPHA_FDR = {"precip": 0.05, "precip_daily": 0.05}  # everything else 0.10 (spatially smooth fields)


def trend_map(cube: xr.DataArray, alpha_fdr: float = 0.10) -> xr.Dataset:
    from statsmodels.stats.multitest import multipletests

    from .trends import ols_ar1_map

    # regular monthly grid so gaps stay gaps (GRACE) and lag-1 is measured between true neighbours
    t = pd.to_datetime(cube.time.values).to_period("M").to_timestamp()
    cube = cube.assign_coords(time=t).groupby("time").mean()
    full = pd.date_range(t.min(), t.max(), freq="MS")
    cube = cube.reindex(time=full)
    ty = (full.year + (full.month - 0.5) / 12).to_numpy(float)
    arr = cube.transpose("time", "lat", "lon").values.astype("float64")
    nt, ny, nx = arr.shape
    flat = arr.reshape(nt, ny * nx)
    finite = np.isfinite(flat)
    nmon = finite.sum(0)
    slope = np.full(ny * nx, np.nan)
    pval = np.full(ny * nx, np.nan)
    r1 = np.full(ny * nx, np.nan)
    cand = np.nonzero((nmon >= MIN_MONTHS) & (np.nanstd(np.where(finite, flat, np.nan), axis=0) > 0))[0]
    if len(cand):
        keys = np.packbits(finite[:, cand], axis=0).T  # one row per cell: its missing-month pattern
        _, group = np.unique(keys, axis=0, return_inverse=True)
        for g in np.unique(group):
            cells = cand[group.ravel() == g]
            rows = finite[:, cells[0]]
            # lag-1 is computed on the compressed rows; with a common mask this only joins across gaps
            sl, pv, rr = ols_ar1_map(flat[rows][:, cells], ty[rows])
            slope[cells], pval[cells], r1[cells] = sl, pv, rr
    q = np.full(ny * nx, np.nan)
    ok = np.isfinite(pval)
    if ok.any():
        q[ok] = multipletests(pval[ok], method="fdr_bh")[1]
    shp = (ny, nx)
    ds = xr.Dataset({
        "slope_per_decade": (("lat", "lon"), slope.reshape(shp).astype("float32")),
        "p_ar1": (("lat", "lon"), pval.reshape(shp).astype("float32")),
        "q_fdr": (("lat", "lon"), q.reshape(shp).astype("float32")),
        "lag1_autocorr": (("lat", "lon"), r1.reshape(shp).astype("float32")),
        "n_months": (("lat", "lon"), nmon.reshape(shp).astype("float32")),
        "mean": cube.mean("time", skipna=True).astype("float32"),
    }, coords={"lat": cube.lat, "lon": cube.lon})
    ds["verdict"] = xr.where(ds.n_months < MIN_MONTHS, -9,
                             xr.where(ds.q_fdr < alpha_fdr, np.sign(ds.slope_per_decade), 0)).astype("int8")
    ds.verdict.attrs["meaning"] = "1 clear rise, -1 clear fall, 0 no clear change yet, -9 too short or no data"
    ds.attrs["alpha_fdr"] = alpha_fdr
    return ds


def quicklook(ds: xr.Dataset, title: str, units: str, path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s = ds.slope_per_decade.where(ds.verdict.isin([-1, 1]))
    lim = float(np.nanpercentile(np.abs(s.values), 98)) if np.isfinite(s.values).any() else 1.0
    fig, ax = plt.subplots(figsize=(12, 6), dpi=110)
    ax.pcolormesh(ds.lon, ds.lat, xr.where(ds.verdict == 0, 1.0, np.nan), cmap="Greys", vmin=0, vmax=3,
                  shading="auto")
    im = ax.pcolormesh(ds.lon, ds.lat, s, cmap="RdBu_r", vmin=-lim, vmax=lim, shading="auto")
    fig.colorbar(im, ax=ax, shrink=0.7, label=f"{units} per decade (significant cells only)")
    ax.set_title(f"{title}\nred/blue: clear trend after FDR (q<{ds.attrs.get('alpha_fdr', 0.1):g}) · "
                 "grey: no clear change yet · white: no data")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(prog="earthpull.trendmap")
    ap.add_argument("--var", required=True, help="variable id from sources.yaml, or 'all'")
    ap.add_argument("--start", default="2003-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--res", type=float, default=0.5, help="output grid in degrees")
    ap.add_argument("--alpha-fdr", type=float, default=None, help="default 0.10, precipitation 0.05")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--include-daily", action="store_true", help="also OMI (thousands of daily files)")
    a = ap.parse_args()

    login()
    cat = load_catalog()
    ids = list(cat) if a.var == "all" else a.var.split(",")
    if os.environ.get("CLOUD_RUN_TASK_INDEX") is not None and len(ids) > 1:  # Cloud Run Job: one variable per task
        ids = [ids[int(os.environ["CLOUD_RUN_TASK_INDEX"])]]
    out = DATA / "trendmaps"
    out.mkdir(parents=True, exist_ok=True)
    for vid in ids:
        if cat[vid]["cadence"] == "daily" and not a.include_daily:
            print(f"[{vid}] skipped (daily; pass --include-daily)")
            continue
        if (out / f"{vid}.done").exists() and not a.force:
            print(f"[{vid}] already done; --force to redo")
            continue
        print(f"[{vid}] building global cube at {a.res} deg")
        try:
            cube, units = build_cube(vid, a.start, a.end, a.res)
            print(f"  cube {dict(cube.sizes)}; testing {cube.sizes['lat'] * cube.sizes['lon']} cells")
            ds = trend_map(cube, a.alpha_fdr if a.alpha_fdr is not None else ALPHA_FDR.get(vid, 0.10))
            ds.attrs.update(variable=vid, name=cat[vid]["name"], source=cat[vid]["instrument"], units=units,
                            start=str(cube.time.values[0])[:7], end=str(cube.time.values[-1])[:7],
                            method="OLS trend + annual/semiannual harmonics; AR(1) effective sample size (Santer 2008); "
                                   f"BH FDR q<{ds.attrs['alpha_fdr']:g} (Wilks 2016)")
            stem = out / f"{vid}_{ds.attrs['start']}_{ds.attrs['end']}"
            ds.to_netcdf(f"{stem}.nc")
            quicklook(ds, f"{cat[vid]['name']} ({cat[vid]['instrument']}), {ds.attrs['start']} to {ds.attrs['end']}",
                      units, f"{stem}.png")
            (out / f"{vid}.done").write_text(str(stem))
            v = ds.verdict.values
            print(f"  wrote {stem}.nc/.png  rise {int((v == 1).sum())}  fall {int((v == -1).sum())}  "
                  f"no clear change {int((v == 0).sum())}")
        except Exception as exc:
            print(f"  failed: {exc}")
            failed = True
    if "failed" in locals():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
