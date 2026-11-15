"""Validate against Liu, Famiglietti et al. (2022), Nature Communications 13:7825,
"Groundwater depletion in California's Central Valley accelerates during megadrought".

Paper (abstract): groundwater loss 2.41 km3/yr for 2003-2021 and 8.58 km3/yr for 2019-2021, from GRACE, over the
Sacramento + San Joaquin + Tulare basins (~154,000 km2). Groundwater = GRACE total water storage minus soil moisture,
snow and surface reservoirs. The per-window mm/yr figures below are the ones quoted by the user's tester.

What this script compares
  A. the old engine on the user's rectangle (ocean cells included)            -> what earth_data.csv showed
  B. the same rectangle with the land mask applied                            -> effect of fix 1
  C. GRACE total water storage over the three USGS basin outlines (HUC4)      -> effect of fix 2 (like-for-like region)
  D. groundwater estimate: C minus GLDAS soil moisture 0-200 cm and snow water -> like-for-like variable
     (reservoirs are not removed: no reservoir data in the tool, so D still includes surface-water change)
"""
import warnings
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from earthpull.core import DATA, BBox, _box_mean, _concept_id, _job_id, _open_var, _raw_dir, _wait, bbox_of, load_catalog, login, pull
from earthpull.trends import _ols_ar1

warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)

basins = gpd.read_file("data/boundaries/wbd/huc4_central_valley.geojson")
poly = basins.union_all()
AREA_KM2 = float(basins.areasqkm.astype(float).sum())
print(f"Region: {', '.join(basins.name)} (USGS WBD HUC4), {AREA_KM2:,.0f} km2")

PAPER = {  # mm/yr of groundwater, as quoted by the tester; km3/yr from the paper's abstract where given
    "2003-09 to 2021-12 (full)": ("2003-09", "2021-12", -15.7, 1.4),
    "2011-08 to 2017-03 (drought)": ("2011-08", "2017-03", -42.7, 5.8),
    "2019-09 to 2021-12 (drought)": ("2019-09", "2021-12", -55.8, 21.8),
    "2003-10 to 2006-07 (recharge)": ("2003-10", "2006-07", 22.7, 16.0),
}


def rate(s: pd.Series, a: str, b: str) -> tuple[float, float, int]:
    """Linear rate (per year) with harmonics and AR(1)-adjusted SE, on the real monthly grid. Returns rate, SE, months."""
    s = s.loc[pd.Period(a, "M"):pd.Period(b, "M")]
    idx = pd.period_range(a, b, freq="M")
    s = s.reindex(idx)
    ty = np.array([p.year + (p.month - 0.5) / 12 for p in idx])
    y = s.to_numpy(float)
    ok = np.isfinite(y)
    f = _ols_ar1(ty, y, ok)
    return f["slope"], f["se"], int(ok.sum())


login()
grace_files = sorted((DATA / "raw" / "_global" / "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4").glob("*.nc"))


def grace_series(bbox, shape=None, mask=True) -> pd.Series:
    da = _open_var(grace_files[0], "lwe_thickness", "land_mask" if mask else None)
    df = _box_mean(da, bbox, shape)
    s = df["value"] * 10.0  # cm -> mm
    s.index = s.index.to_period("M")
    return s.groupby(level=0).mean()


user_box = BBox(-125.42, 31.579, -112.677, 42.94)  # the box behind earth_data.csv (data/last_run/run.json)
series = {
    "A. old engine, user's box, ocean included": grace_series(user_box, mask=False),
    "B. user's box, land only": grace_series(user_box, mask=True),
    "C. basin outlines, land only (total water)": grace_series(bbox_of(poly), poly, mask=True),
}

# D. groundwater estimate: GLDAS soil moisture (4 layers, 0-200 cm) + snow water over the basins, in one Harmony job
gl_vars = ["SoilMoi0_10cm_inst", "SoilMoi10_40cm_inst", "SoilMoi40_100cm_inst", "SoilMoi100_200cm_inst", "SWE_inst"]
src = load_catalog()["soil_moisture"]
fbox = bbox_of(poly, 1.0)
out = _raw_dir("gldas_storage_cv", fbox, "2002-04-01", "2021-12-31")
done = out / ".complete"
if not done.exists():
    from harmony import BBox as HB, Client, Collection, Request
    c = Client()
    req = Request(collection=Collection(id=_concept_id(src)), spatial=HB(*fbox.tuple()),
                  temporal={"start": datetime(2002, 4, 1), "stop": datetime(2021, 12, 31)}, variables=gl_vars)
    job = _job_id(c.submit(req))
    _wait(c, job, "GLDAS storage")
    for f in c.download_all(job, directory=str(out), overwrite=False):
        f.result()
    done.touch()
gl = {}
for v in gl_vars:
    parts = [_box_mean(_open_var(p, v), bbox_of(poly), poly) for p in sorted(out.glob("*.nc4"))]
    d = pd.concat(parts).sort_index()
    s = d["value"]
    s.index = s.index.to_period("M")
    gl[v] = s.groupby(level=0).mean()
gl = pd.DataFrame(gl)
store = gl.sum(axis=1)  # kg/m2 = mm of water, 0-200 cm soil + snow
base = store.loc["2004-01":"2009-12"].mean()  # GRACE anomalies are relative to 2004.0-2009.999
store_anom = store - base
tws = series["C. basin outlines, land only (total water)"]
series["D. groundwater estimate (C minus soil 0-200 cm and snow)"] = (tws - store_anom.reindex(tws.index))

# ---------------------------------------------------------------- compare
rows = []
for period, (a, b, p_mm, p_se) in PAPER.items():
    months = len(pd.period_range(a, b, freq="M"))
    for name, s in series.items():
        r, se, n = rate(s, a, b)
        rows.append({"period": period, "series": name, "rate mm/yr": r, "+/- (1 SE)": se,
                     "km3/yr": r * AREA_KM2 / 1e6, "months with data": n,
                     "paper mm/yr": p_mm, "paper +/-": p_se, "ratio to paper": r / p_mm,
                     "engine verdict": "rate only: under 10 years" if months < 120 else "full trend test applies"})
tab = pd.DataFrame(rows)
print(tab.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
tab.to_csv("data/out/validate_liu2022.csv", index=False)
print(f"\nPaper abstract: 2.41 km3/yr (2003-2021) and 8.58 km3/yr (2019-2021) of groundwater loss; "
      f"over {AREA_KM2:,.0f} km2 that is {2.41e6 / AREA_KM2:.1f} and {8.58e6 / AREA_KM2:.1f} mm/yr.")
print(f"Soil (0-200 cm) + snow storage trend 2003-09 to 2021-12: {rate(store, '2003-09', '2021-12')[0]:+.2f} mm/yr")
