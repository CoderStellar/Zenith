"""Build a local global cube for a variable (all months, native grid, one variable) so any box is a local slice.

  python -m earthpull.cubes air_temp aerosol --start 1980-01-01 --end 2025-12-31

Worth it for MERRA-2 (no Giovanni averaging, so every new box otherwise needs a ~10 minute NASA job).
A MERRA-2 variable is about 200 KB per month, so 46 years is about 110 MB.
"""
import argparse

import xarray as xr

from .core import DATA, BBox, _clip_dates, _fetch_harmony, _open_var, _raw_dir, _standardize, load_catalog, login

GLOBE = BBox(-180, -90, 180, 90)


def build(vid: str, start: str, end: str):
    src = dict(load_catalog()[vid])
    src.setdefault("harmony_variable", src["variable"])
    start, end = _clip_dates(src, start, end)
    paths = _fetch_harmony(src, GLOBE, start, end, _raw_dir(vid, GLOBE, start, end))
    das = [_standardize(_open_var(p, src["variable"], src.get("mask_var"))) for p in paths]
    cube = xr.concat(das, "time").sortby("time").astype("float32")
    if cube.sizes["lon"] < 100 or cube.sizes["lat"] < 50:  # guard against a bad (clipped) global subset
        raise RuntimeError(f"{vid}: global cube looks clipped {dict(cube.sizes)}; not saving")
    units = das[0].attrs.get("units", src.get("units", ""))
    out = DATA / "cubes"
    out.mkdir(parents=True, exist_ok=True)
    ds = cube.to_dataset(name=src["variable"])
    ds[src["variable"]].attrs["units"] = units
    ds.attrs.update(variable=vid, source=src["instrument"], start=start, end=end)
    tmp = out / f"{vid}.nc.tmp"
    ds.to_netcdf(tmp, encoding={src["variable"]: {"zlib": True, "complevel": 3}})
    tmp.rename(out / f"{vid}.nc")
    print(f"[{vid}] cube {dict(cube.sizes)} -> {out / f'{vid}.nc'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--start", default="1980-01-01")
    ap.add_argument("--end", default="2025-12-31")
    a = ap.parse_args()
    login()
    for v in a.ids:
        build(v, a.start, a.end)
