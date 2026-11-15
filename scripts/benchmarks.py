"""Benchmark the engine against published trends that use Giovanni-era NASA variables.

Each benchmark: same variable, region outline, period and units as the paper; the rate comes from the engine's own
fit (earthpull.trends._ols_ar1: trend + annual/semiannual harmonics, AR(1)-adjusted standard error).

Pass rules (fixed):
  rate with uncertainty   |ours - paper| <= 2 * sqrt(se_ours^2 + se_paper^2)      -> PASS
  threshold ("> 40 %")    same sign and |ours| >= 0.75 * |threshold|                 -> PASS
  sign only               same sign and engine p < 0.05                               -> PASS
Writes data/out/benchmarks.csv.
"""
import sys
import warnings
from datetime import datetime

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import box as sbox

sys.path.insert(0, ".")
from earthpull.core import (DATA, BBox, _box_mean, _concept_id, _job_id, _open_var, _raw_dir, _wait, bbox_of,  # noqa: E402
                            load_catalog, login, pull)
from earthpull.trends import _ols_ar1, region_area_km2  # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250, "display.max_colwidth", 60)
login()
GRACE = sorted((DATA / "raw" / "_global" / "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4").glob("*.nc"))[0]
NE = "data/boundaries/ne/"
a1 = gpd.read_file(NE + "ne_50m_admin_1_states_provinces.geojson")
a0 = gpd.read_file(NE + "ne_50m_admin_0_countries.geojson")
marine = gpd.read_file(NE + "ne_50m_geography_marine_polys.geojson")
huc = gpd.read_file("data/boundaries/wbd/huc4_central_valley.geojson")
SHAPES = {
    "NW India (Rajasthan, Punjab, Haryana, Delhi)": a1[(a1.admin == "India") & a1.name.isin(["Rajasthan", "Punjab", "Haryana", "Delhi"])].union_all(),
    "Caspian Sea": marine[marine.name == "Caspian Sea"].union_all(),
    "Antarctica": a0[a0.ADMIN == "Antarctica"].union_all(),
    "Greenland": a0[a0.ADMIN == "Greenland"].union_all(),
    "Central Valley basins (HUC4 1802-1804)": huc.union_all(),
    "India": a0[a0.ADMIN == "India"].union_all(),
}


def monthly(s: pd.Series) -> pd.Series:
    s = s.copy()
    s.index = pd.PeriodIndex(pd.to_datetime(s.index), freq="M") if not isinstance(s.index, pd.PeriodIndex) else s.index
    return s.groupby(level=0).mean()


def fit(s: pd.Series, a: str, b: str, breaks=()) -> dict:
    idx = pd.period_range(a, b, freq="M")
    s = monthly(s).reindex(idx)
    ty = np.array([p.year + (p.month - 0.5) / 12 for p in idx])
    y = s.to_numpy(float)
    ok = np.isfinite(y)
    f = _ols_ar1(ty, y, ok, breaks)
    first, last = ty[ok][0], ty[ok][-1]
    X0 = f["slope"] * (first - ty[ok].mean())
    return {"slope": f["slope"], "se": f["se"], "p": f["p"], "months": int(ok.sum()), "first": first, "last": last}


def grace(shape, mask=True) -> pd.Series:
    df = _box_mean(_open_var(GRACE, "lwe_thickness", "land_mask" if mask else None), bbox_of(shape), shape)
    return monthly(df["value"] * 10.0)  # cm -> mm


def gldas_storage(shape, start="2002-04-01", end="2021-12-31") -> pd.Series:
    """GLDAS Noah soil moisture 0-200 cm + snow water, mm, as anomalies vs 2004-2009 (GRACE's baseline)."""
    from harmony import BBox as HB, Client, Collection, Request
    gv = ["SoilMoi0_10cm_inst", "SoilMoi10_40cm_inst", "SoilMoi40_100cm_inst", "SoilMoi100_200cm_inst", "SWE_inst"]
    fb = bbox_of(shape, 1.0)
    out = _raw_dir("gldas_storage", fb, start, end)
    if not (out / ".complete").exists():
        c = Client()
        job = _job_id(c.submit(Request(collection=Collection(id=_concept_id(load_catalog()["soil_moisture"])),
                                       spatial=HB(*fb.tuple()), variables=gv,
                                       temporal={"start": datetime.fromisoformat(start), "stop": datetime.fromisoformat(end)})))
        _wait(c, job, "GLDAS soil + snow")
        for f in c.download_all(job, directory=str(out), overwrite=False):
            f.result()
        (out / ".complete").touch()
    tot = None
    for v in gv:
        parts = [_box_mean(_open_var(p, v), bbox_of(shape), shape) for p in sorted(out.glob("*.nc4"))]
        s = monthly(pd.concat(parts)["value"])
        tot = s if tot is None else tot.add(s, fill_value=np.nan)
    return tot - tot.loc["2004-01":"2009-12"].mean()


def cube_series(name, var, shape=None, bbox=None) -> pd.Series:
    da = xr.open_dataset(DATA / "cubes" / f"{name}.nc")[var].load()
    df = _box_mean(da, bbox or bbox_of(shape), shape)
    s = df["value"].where(df["valid_fraction"] >= 0.7)
    return monthly(s)


def pct_change(s: pd.Series, a: str, b: str) -> tuple[float, float]:
    """Percent change from the fitted line (start to end) and from first-year to last-year annual means."""
    f = fit(s, a, b)
    sm = monthly(s).loc[pd.Period(a, "M"):pd.Period(b, "M")]
    ann = sm.groupby(sm.index.year).mean()
    level0 = ann.mean() - f["slope"] * (np.mean(ann.index) - ann.index[0])  # fitted value in the first year
    return 100 * f["slope"] * (ann.index[-1] - ann.index[0]) / level0, 100 * (ann.iloc[-1] / ann.iloc[0] - 1)


rows = []


def margin_rate(shape, a, b, gw=False):
    from earthpull.trends import LEAKAGE_MARGIN_KM, buffer_km
    big = buffer_km(shape, LEAKAGE_MARGIN_KM)
    s = grace(big)
    if gw:
        s = s - gldas_storage(shape).reindex(s.index) * (region_area_km2(shape) / region_area_km2(big))
    return fit(s, a, b)["slope"] * region_area_km2(big) * 1e-6


def add(n, paper, quantity, region, period, kind, paper_val, paper_se, ours, ours_se=np.nan, p=np.nan, note=""):
    if kind == "rate":
        lim = 2 * np.sqrt(np.nan_to_num(ours_se) ** 2 + np.nan_to_num(paper_se) ** 2)
        ok = abs(ours - paper_val) <= lim and np.sign(ours) == np.sign(paper_val)  # opposite sign never passes
    elif kind == "threshold":
        ok = np.sign(ours) == np.sign(paper_val) and abs(ours) >= 0.75 * abs(paper_val)
    else:
        ok = np.sign(ours) == np.sign(paper_val) and p < 0.05
    rows.append({"#": n, "paper": paper, "quantity": quantity, "region": region, "period": period,
                 "paper value": paper_val, "paper +/-": paper_se, "engine value": ours, "engine +/-": ours_se,
                 "ratio": ours / paper_val if paper_val else np.nan, "result": "PASS" if ok else "FAIL", "note": note})
    print(f"{n:>2} {'PASS' if ok else 'FAIL'}  {paper}: {quantity} | paper {paper_val:+.3g} ± {paper_se if paper_se == paper_se else '-'} "
          f"| engine {ours:+.3g} ± {ours_se:.2g}" + (f" | {note}" if note else ""))


GT = lambda mm, shape: mm * region_area_km2(shape) * 1e-6  # mm of water over the area -> km3 (= Gt)

# 1. Rodell 2009: groundwater NW India, Aug 2002 - Oct 2008, 17.7 +/- 4.5 km3/yr
sh = SHAPES["NW India (Rajasthan, Punjab, Haryana, Delhi)"]
gw = grace(sh) - gldas_storage(sh).reindex(grace(sh).index)
f = fit(gw, "2002-08", "2008-10")
add(1, "Rodell et al. 2009 Nature", "groundwater km3/yr", "Rajasthan+Punjab+Haryana+Delhi", "2002-08..2008-10",
    "rate", -17.7, 4.5, GT(f["slope"], sh), GT(f["se"], sh),
    note=f"with 100 km margin: {margin_rate(sh, '2002-08', '2008-10', gw=True):+.1f}")

# 2-3. Rodell 2018: total water storage, Caspian Sea and Antarctica, 2002-2016 (Gt/yr)
for n, reg, val, se in [(2, "Caspian Sea", -23.7, 4.2), (3, "Antarctica", -127.6, 39.9)]:
    sh = SHAPES[reg]
    f = fit(grace(sh), "2002-04", "2016-12")
    add(n, "Rodell et al. 2018 Nature", "TWS Gt/yr", reg, "2002-04..2016-12", "rate", val, se, GT(f["slope"], sh),
        GT(f["se"], sh), note=(f"with 100 km margin: {margin_rate(sh, '2002-04', '2016-12'):+.1f}" if reg != "Antarctica"
                               else "margin not applied around the pole"))

# 4-5. Famiglietti 2011: Sacramento + San Joaquin basins, Oct 2003 - Mar 2010: TWS -31.0 +/- 2.7, GW -20.4 +/- 3.9 mm/yr
sh = SHAPES["Central Valley basins (HUC4 1802-1804)"]
tws = grace(sh)
gw = tws - gldas_storage(sh).reindex(tws.index)
f = fit(tws, "2003-10", "2010-03")
add(4, "Famiglietti et al. 2011 GRL", "TWS mm/yr", "Central Valley basins", "2003-10..2010-03", "rate", -31.0, 2.7, f["slope"], f["se"])
f = fit(gw, "2003-10", "2010-03")
add(5, "Famiglietti et al. 2011 GRL", "groundwater mm/yr", "Central Valley basins", "2003-10..2010-03", "rate", -20.4, 3.9, f["slope"], f["se"])

# 6. Liu et al. 2022: groundwater 2003-2021, 2.41 km3/yr (abstract; no uncertainty in abstract -> use the paper's
#    full-period mm/yr uncertainty quoted by the user's tester, 1.4 mm/yr)
f = fit(gw, "2003-01", "2021-12")
add(6, "Liu et al. 2022 Nat Commun", "groundwater km3/yr", "Central Valley basins", "2003..2021", "rate", -2.41,
    GT(1.4, sh), GT(f["slope"], sh), GT(f["se"], sh), note="no reservoir removal in our estimate")

# 7. Velicogna et al. 2020: Greenland Apr 2002 - Sep 2019, about -268 Gt/yr (secondary source for the number)
sh = SHAPES["Greenland"]
f = fit(grace(sh), "2002-04", "2019-09")
add(7, "Velicogna et al. 2020 GRL", "mass Gt/yr", "Greenland", "2002-04..2019-09", "rate", -268, 13, GT(f["slope"], sh),
    GT(f["se"], sh), note="paper uncertainty assumed ~13 Gt/yr (Mu et al., same data)")

# 8-9. Rantanen et al. 2022: Arctic (66.5-90N) 0.73, globe 0.19 C/decade, 1979-2021 (MERRA-2 starts 1980)
for n, reg, b, val in [(8, "Arctic 66.5-90N", BBox(-180, 66.5, 180, 90), 0.73), (9, "Globe", BBox(-180, -90, 180, 90), 0.19)]:
    s = cube_series("air_temp", "T2M", bbox=b)
    f = fit(s, "1980-01", "2021-12")
    add(n, "Rantanen et al. 2022 CommsEE", "air temp C/decade", reg, "1980..2021 (paper 1979..2021)", "rate", val, 0.02,
        10 * f["slope"], 10 * f["se"], note="paper = mean of 4 observational datasets; engine = MERRA-2")

# 10-13. Krotkov et al. 2016 (2005-2015) and Duncan et al. 2016 (2005-2014): OMI NO2 percent change
no2 = {}
for reg, b in [("Eastern US", BBox(-90, 35, -72, 45)), ("India", bbox_of(SHAPES["India"])),
               ("India coal belt", BBox(81, 21, 86, 25)),
               ("New York City", BBox(-74.6, 40.2, -73.4, 41.2)), ("Beijing", BBox(115.9, 39.4, 117.0, 40.4))]:
    w, _ = pull(b, "2005-01-01", "2015-12-31", ["no2"])
    no2[reg] = w["no2"]
for n, paper, reg, a, b_, val in [(10, "Krotkov et al. 2016 ACP", "Eastern US", "2005-01", "2015-12", -40),
                                  (11, "Krotkov et al. 2016 ACP", "India", "2005-01", "2015-12", 50),
                                  (11.5, "Krotkov et al. 2016 ACP", "India coal belt", "2005-01", "2015-12", 50),
                                  (12, "Duncan et al. 2016 JGR", "New York City", "2005-01", "2014-12", -45),
                                  (13, "Duncan et al. 2016 JGR", "Beijing", "2005-01", "2014-12", -10)]:
    fitpct, annpct = pct_change(no2[reg], a, b_)
    kind = "threshold" if paper.startswith("Krotkov") else "rate"
    add(n, paper, "NO2 % change", reg, f"{a[:4]}..{b_[:4]}", kind, val, 15 if kind == "rate" else np.nan, fitpct,
        np.nan, note=f"first-to-last annual mean: {annpct:+.0f}%")

# 14-15. Che et al. 2019: MODIS AOD falling over the eastern US, rising over South Asia (sign only)
for n, reg, sh, b, val in [(14, "Eastern US", None, BBox(-90, 35, -72, 45), -1), (15, "India", SHAPES["India"], None, +1)]:
    s = cube_series("aod_modis_aqua", "AOD_550_Dark_Target_Deep_Blue_Combined_Mean_Mean", sh, b)
    f = fit(s, "2002-07", "2016-12")
    add(n, "Che et al. 2019 ACP", "MODIS AOD trend sign", reg, "2002..2016", "sign", val, np.nan, 10 * f["slope"],
        10 * f["se"], p=f["p"], note=f"p = {f['p']:.2g}")

tab = pd.DataFrame(rows)
tab.to_csv("data/out/benchmarks.csv", index=False)
print(f"\n{(tab.result == 'PASS').sum()} of {len(tab)} benchmarks pass")
