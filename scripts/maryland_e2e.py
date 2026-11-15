"""End-to-end test: Maryland state-average monthly 2 m air temperature (MERRA-2 M2TMNXSLV T2M),
seasonally adjusted Theil-Sen slope with 95% CI, and Mann-Kendall tests.

Inputs: the 264 monthly MERRA-2 files already subset to a box around Maryland (data/raw/air_temp/55a0ae590b_*),
and the US Census 2024 cartographic state boundaries (cb_2024_us_state_500k.zip).
"""
import glob
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import pymannkendall as mk
import regionmask
import xarray as xr
from scipy import stats

warnings.filterwarnings("ignore")

# 1. Data: monthly T2M on the native MERRA-2 grid (0.5 lat x 0.625 lon), Kelvin
files = sorted(glob.glob("data/raw/air_temp/55a0ae590b_2003-01-01_2024-12-31/*.nc4"))
t2m = xr.open_mfdataset(files, combine="by_coords")["T2M"].load() - 273.15  # to deg C

# 2. Maryland polygon from the Census file; fractional cell coverage x cos(latitude) as area weights
states = gpd.read_file("zip://data/boundaries/cb_2024_us_state_500k.zip")
md = states[states.STUSPS == "MD"]
region = regionmask.from_geopandas(md, names="NAME", abbrevs="STUSPS")
frac = region.mask_3D_frac_approx(t2m.lon, t2m.lat).isel(region=0)  # 0..1 share of each cell inside MD
weights = frac * np.cos(np.deg2rad(t2m.lat))
print(f"cells touching MD: {int((frac > 0).sum())}, effective cells: {float(frac.sum()):.1f}")
series = t2m.weighted(weights.fillna(0)).mean(("lat", "lon")).to_series()
series.index = pd.to_datetime(series.index).to_period("M")

# 3. Seasonal adjustment: subtract each calendar month's mean over the record
anom = series - series.groupby(series.index.month).transform("mean")
t_years = np.array([(p.year - series.index[0].year) + (p.month - 1) / 12 for p in series.index])

# 4. Theil-Sen slope with 95% CI (scipy), per decade
slope, intercept, lo, hi = stats.theilslopes(anom.values, t_years, alpha=0.95)

# 5. Mann-Kendall tests (pymannkendall)
mk_orig = mk.original_test(anom.values)
mk_hr = mk.hamed_rao_modification_test(anom.values)  # corrects for autocorrelation
mk_seas = mk.seasonal_test(series.values, period=12)  # on raw monthly values, by calendar month
lr = stats.linregress(t_years, anom.values)  # OLS t-test, for comparison

print(f"record: {series.index[0]} to {series.index[-1]}, {len(series)} months ({len(series) / 12:.0f} years), missing {int(series.isna().sum())}")
print(f"Maryland mean annual temperature: {series.mean():.2f} C")
print(f"Theil-Sen slope: {slope * 10:+.3f} C per decade  (95% CI {lo * 10:+.3f} to {hi * 10:+.3f})")
print(f"Mann-Kendall original:  p = {mk_orig.p:.2e}  trend = {mk_orig.trend}")
print(f"Mann-Kendall Hamed-Rao: p = {mk_hr.p:.2e}  trend = {mk_hr.trend}")
print(f"Seasonal Mann-Kendall:  p = {mk_seas.p:.2e}  seasonal Sen slope = {mk_seas.slope * 10:+.3f} C per decade")
print(f"OLS t-test:             p = {lr.pvalue:.2e}  slope = {lr.slope * 10:+.3f} C per decade")
series.to_csv("data/out/maryland_state_t2m_merra2_2003_2024.csv", header=["t2m_C"])
