"""Reproduce the challenge video's example and test it with our tools.

Video: MODIS Aqua aerosol optical depth (AOD), monthly, averaged over the state of Wisconsin since 2002 (made in
Giovanni). Claim: "AOD over Wisconsin may be increasing in the summer months", linked to smoke from wildfires in
central Canada.

Steps
1. Wisconsin state-average monthly AOD from the local MODIS Aqua cube (MYD08_M3 v6.1, 1 degree), weighted by
   each cell's share inside the Census state outline x cos(latitude), like Giovanni's shape masks.
2. Trends: all months (earthpull.trends.trend_report), each season and each calendar month (season_trend), plus
   the plain p-value the video describes, for comparison.
3. Links: central-Canada AOD vs Wisconsin AOD with the correlation engine (seasons and trends removed, effective
   sample size, FDR across delays), and whether Wisconsin's summer trend survives accounting for Canada's.
"""
import warnings

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import regionmask
import xarray as xr

from earthpull import engine
from earthpull.core import BBox, _box_mean
from earthpull.trends import SEASONS, season_series, season_trend, trend_report

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
VAR = "AOD_550_Dark_Target_Deep_Blue_Combined_Mean_Mean"
cube = xr.open_dataset("data/cubes/aod_modis_aqua.nc")[VAR].load()
print(f"cube: {dict(cube.sizes)}, {str(cube.time.values[0])[:7]} to {str(cube.time.values[-1])[:7]}")


def state_mean(abbr: str) -> pd.Series:
    states = gpd.read_file("zip://data/boundaries/cb_2024_us_state_500k.zip")
    reg = regionmask.from_geopandas(states[states.STUSPS == abbr], names="NAME", abbrevs="STUSPS")
    frac = reg.mask_3D_frac_approx(cube.lon, cube.lat).isel(region=0)
    w = (frac * np.cos(np.deg2rad(cube.lat))).fillna(0)
    valid = cube.notnull()
    num = (cube.fillna(0) * w).sum(("lat", "lon"))
    den = (valid * w).sum(("lat", "lon"))
    cover = den / w.sum()
    s = (num / den).where(cover >= 0.7).to_series()  # blank months with under 70% of the state observed
    s.index = pd.to_datetime(s.index).to_period("M")
    print(f"{abbr}: {int((frac > 0).sum())} cells touch the state, {float(frac.sum()):.1f} effective 1-degree cells; "
          f"{int(s.isna().sum())} months blanked for low coverage")
    return s


def box_mean(b: BBox) -> pd.Series:
    df = _box_mean(cube, b)
    s = df["value"].where(df["valid_fraction"] >= 0.7)
    s.index = s.index.to_period("M")
    return s


wi = state_mean("WI")
canada = box_mean(BBox(-110, 49, -80, 60))  # central Canada boreal fire region (Saskatchewan, Manitoba, NW Ontario)
first, last = wi.first_valid_index(), wi.last_valid_index()
print(f"Wisconsin record: {first} to {last}, {int(wi.notna().sum())} months with data")

# ---------------------------------------------------------------- 1. the time series (like the Giovanni plot)
fig, ax = plt.subplots(2, 1, figsize=(11, 6.5), dpi=110, gridspec_kw={"height_ratios": [2, 1.3]})
x = wi.index.to_timestamp()
ax[0].plot(x, wi.values, color="#1c7ed6", lw=1)
summer = wi[wi.index.month.isin([6, 7, 8])]
ax[0].scatter(summer.index.to_timestamp(), summer.values, s=10, color="#d9480f", zorder=3, label="Jun-Aug months")
ax[0].set_title("Wisconsin state-average aerosol optical depth, MODIS Aqua (MYD08_M3 v6.1), monthly")
ax[0].set_ylabel("AOD (550 nm)")
ax[0].legend(loc="upper left")
jja = season_series(wi, (6, 7, 8))
ax[1].bar(jja.index, jja.values, color="#d9480f")
ax[1].set_title("Summer (June-August) mean, one bar per year")
ax[1].set_ylabel("AOD")
fig.tight_layout()
fig.savefig("data/out/video_example_wisconsin_aod.png")
print("plot: data/out/video_example_wisconsin_aod.png")

# ---------------------------------------------------------------- 2. trends
print("\n=== TRENDS (memory-adjusted test + Theil-Sen agreement) ===")
r = trend_report(wi)
print(f"All months: {r['slope_per_decade']:+.4f} AOD/decade (95% {r['ci_low']:+.4f} to {r['ci_high']:+.4f}), "
      f"p = {r['p_ar1']:.3g}; plain t-test p = {r['p_ttest']:.3g}; month-to-month memory r1 = {r['lag1_autocorr']:.2f}")
rows = []
for name, months in SEASONS.items():
    t = season_trend(wi, months)
    rows.append({"period": name, "years": t["years"], "mean AOD": t.get("mean"),
                 "per decade": t.get("slope_per_decade"), "95% low": t.get("ci_low"), "95% high": t.get("ci_high"),
                 "% of mean per decade": t.get("pct_of_mean_per_decade"), "p (memory-adjusted)": t.get("p"),
                 "plain p (video method)": t.get("p_ttest"), "verdict": t["verdict"]})
for m in range(1, 13):
    t = season_trend(wi, (m,))
    rows.append({"period": pd.Timestamp(2000, m, 1).strftime("%B"), "years": t["years"], "mean AOD": t.get("mean"),
                 "per decade": t.get("slope_per_decade"), "95% low": t.get("ci_low"), "95% high": t.get("ci_high"),
                 "% of mean per decade": t.get("pct_of_mean_per_decade"), "p (memory-adjusted)": t.get("p"),
                 "plain p (video method)": t.get("p_ttest"), "verdict": t["verdict"]})
tab = pd.DataFrame(rows)
print(tab.to_string(index=False, float_format=lambda v: f"{v:.3g}"))
tab.to_csv("data/out/video_example_trends.csv", index=False)
print("\nSummer means by year:", {int(k): round(float(v), 3) for k, v in jja.items()})

# ---------------------------------------------------------------- 3. links: central Canada -> Wisconsin
print("\n=== LINK: central Canada AOD -> Wisconsin AOD (correlation engine) ===")
w = pd.DataFrame({"canada": canada, "wisconsin": wi})
_, det = engine.prepare(w)
lt = engine.pair_lags(det, "canada", "wisconsin", 2)
from statsmodels.stats.multitest import multipletests  # noqa: E402

lt["q"] = multipletests(lt.p, method="fdr_bh")[1]
print("All months, seasons and trends removed (positive lag = Wisconsin later):")
print(lt[["lag", "r", "n_eff", "q"]].to_string(index=False, float_format=lambda v: f"{v:.3g}"))
best = lt.loc[lt.r.abs().idxmax()]
sp = engine.surrogate_p(det, "canada", "wisconsin", int(best.lag), best.r, 1000)
print(f"best: lag {int(best.lag)}, r = {best.r:.2f}, surrogate p = {sp:.3g}")
# summer months only
summer_mask = det.index.month.isin([6, 7, 8])
a, b = det["canada"][summer_mask].values, det["wisconsin"][summer_mask].values
ok = np.isfinite(a) & np.isfinite(b)
print(f"Summer months only (same month): r = {np.corrcoef(a[ok], b[ok])[0, 1]:.2f}, n = {int(ok.sum())}")
# composite: Wisconsin in Canada's smokiest months
thr = det["canada"].quantile(0.9)
hi = det["wisconsin"][det["canada"] >= thr]
rest = det["wisconsin"][det["canada"] < thr]
from scipy import stats  # noqa: E402

print(f"When Canada AOD is in its top 10% ({len(hi)} months), Wisconsin AOD anomaly averages {hi.mean():+.3f} vs "
      f"{rest.mean():+.3f} otherwise (Mann-Whitney p = {stats.mannwhitneyu(hi.dropna(), rest.dropna()).pvalue:.2g})")
print("Smokiest Canada months:", ", ".join(str(p) for p in det["canada"].nlargest(8).index))

# does Wisconsin's summer trend survive accounting for Canada's summer AOD?
ca_jja = season_series(canada, (6, 7, 8))
both = pd.DataFrame({"wi": jja, "ca": ca_jja}).dropna()
import statsmodels.api as sm  # noqa: E402

t = both.index.to_numpy(float)
m0 = sm.OLS(both.wi, sm.add_constant(t)).fit()
m1 = sm.OLS(both.wi, sm.add_constant(np.c_[t, both.ca])).fit()
print(f"\nSummer means: Canada vs Wisconsin r = {both.wi.corr(both.ca):.2f} ({len(both)} years)")
print(f"Wisconsin summer trend alone: {10 * m0.params.iloc[1]:+.4f}/decade (p = {m0.pvalues.iloc[1]:.3g}); "
      f"after accounting for Canada's summer AOD: {10 * m1.params.iloc[1]:+.4f}/decade (p = {m1.pvalues.iloc[1]:.3g}); "
      f"Canada effect p = {m1.pvalues.iloc[2]:.3g}")
print(f"Canada summer trend: {season_trend(canada, (6, 7, 8))['slope_per_decade']:+.4f}/decade, "
      f"p = {season_trend(canada, (6, 7, 8))['p']:.3g}")
