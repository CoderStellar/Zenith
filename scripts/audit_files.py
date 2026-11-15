"""Open every downloaded product group and report dims, variables, units, dates, missing values,
and samples at a US point (College Park, MD: 38.99 N, -76.94 E)."""
import glob, re, warnings
import numpy as np, pandas as pd, xarray as xr, netCDF4
warnings.filterwarnings("ignore")
LAT, LON = 38.99, -76.94

def walk(nc, path=""):
    for n, v in nc.variables.items():
        yield f"{path}/{n}", v
    for g, sub in nc.groups.items():
        yield from walk(sub, f"{path}/{g}")

def nc_group(files, var, label):
    files = sorted(files)
    dates = sorted(re.search(r"\.(\d{6})_", f).group(1) for f in files if re.search(r"\.(\d{6})_", f))
    ds = xr.open_mfdataset(files, combine="by_coords") if var in xr.open_dataset(files[0]) else None
    da = ds[var].load()
    miss = int(da.isnull().sum()); tot = int(da.size)
    print(f"\n### {label}: {len(files)} files, months {dates[0]}..{dates[-1]}")
    print(f"dims {dict(da.sizes)}  lat {float(da.lat.min()):.2f}..{float(da.lat.max()):.2f}  lon {float(da.lon.min()):.3f}..{float(da.lon.max()):.3f}  units={da.attrs.get('units')}  missing {miss}/{tot}")
    if da.lat.min() <= LAT <= da.lat.max() and da.lon.min() <= LON <= da.lon.max():
        p = da.sel(lat=LAT, lon=LON, method="nearest")
        print(f"sample at nearest cell ({float(p.lat):.2f}, {float(p.lon):.3f}):")
        print(p.to_series().head(5).to_string())
    else:
        print("no US sample: this box is not in the US")

def giovanni_csv(f, label):
    lines = open(f).read().splitlines()
    h = next(i for i, l in enumerate(lines) if l.startswith("time,"))
    meta = {l.split(",")[0].rstrip(":"): l.split(",", 1)[1] for l in lines[:h] if "," in l and l.split(",")[0]}
    df = pd.read_csv(f, skiprows=h)
    fill = float(meta.get("Fill Value", "nan"))
    v = df.iloc[:, 1]; nmiss = int((v.isna() | np.isclose(v, fill)).sum())
    print(f"\n### {label}: {f.split('/')[-1][:95]}")
    print(f"box {meta.get('User Bounding Box')}  rows {len(df)}  {df.time.iloc[0][:10]}..{df.time.iloc[-1][:10]}  column {df.columns[1]}  missing {nmiss}")
    print(df.head(5).to_string(index=False))

R = "data/raw"
nc_group(glob.glob(f"{R}/air_temp/55a0ae590b*/*.nc4"), "T2M", "MERRA-2 M2TMNXSLV T2M, Maryland box")
nc_group(glob.glob(f"{R}/air_temp/a6cefd1be4*/*.nc4"), "T2M", "MERRA-2 M2TMNXSLV T2M, N. India box")
nc_group(glob.glob(f"{R}/air_temp/8be2fb0298*/*.nc4"), "T2M", "MERRA-2 M2TMNXSLV T2M, partial box (19 files)")
nc_group(glob.glob(f"{R}/aerosol/55a0ae590b*/*.nc4"), "TOTEXTTAU", "MERRA-2 M2TMNXAER TOTEXTTAU, Maryland box")
nc_group(glob.glob(f"{R}/aerosol/a6cefd1be4*/*.nc4"), "TOTEXTTAU", "MERRA-2 M2TMNXAER TOTEXTTAU, N. India box")
for f in sorted(glob.glob(f"{R}/*/55a0ae590b*/*.csv")) + sorted(glob.glob(f"{R}/aerosol_daily/*/*.csv")):
    giovanni_csv(f, f.split("/")[2])

g = xr.open_dataset(glob.glob(f"{R}/_global/TELLUS*/*.nc")[0])
lwe = g["lwe_thickness"]
print(f"\n### GRACE/GRACE-FO JPL mascon CRI RL06.3 v04: dims {dict(lwe.sizes)} units={lwe.attrs.get('units')} time {str(g.time.values[0])[:10]}..{str(g.time.values[-1])[:10]} missing {int(lwe.isnull().sum())}/{lwe.size}")
p = lwe.sel(lat=LAT, lon=(LON + 360) % 360, method="nearest")
print(p.to_series().head(5).to_string())
from pyhdf.SD import SD, SDC
for f in sorted(glob.glob(f"{R}/_global/MOD1*/*.hdf")):
    sd = SD(f, SDC.READ); name = "CMG 0.05 Deg Monthly NDVI" if "MOD13" in f else "LST_Day_CMG"
    s = sd.select(name); a = s.attributes(); arr = s.get()
    print(f"\n### {f.split('/')[-1]}: {name} shape {arr.shape} units={a.get('units')} scale={a.get('scale_factor')} fill={a.get('_FillValue')} fill-count {int((arr == a.get('_FillValue')).sum())}/{arr.size}")
for f in sorted(glob.glob(f"{R}/_inspect/*")):
    print(f"\n### inspect sample: {f.split('/')[-1]} ({round(__import__('os').path.getsize(f)/1e6,1)} MB)")
