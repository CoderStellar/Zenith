"""Run the correlation engine on the two cached regions (no downloads: everything comes from the local cache)."""
import time, warnings
import pandas as pd
from earthpull.core import BBox, load_catalog, pull
from earthpull import engine
warnings.filterwarnings("ignore")
pd.set_option("display.width", 250, "display.max_colwidth", 90)
cat = load_catalog()
names = {k: v["name"] for k, v in cat.items()}
VARS = ["air_temp", "aerosol", "precip", "soil_moisture", "evaporation", "surface_air_temp_airs", "no2", "water_storage"]
for label, box in [("MARYLAND / CHESAPEAKE", BBox(-79.585, 37.858, -74.686, 39.809)), ("NORTHERN INDIA", BBox(70, 24, 90, 32))]:
    t0 = time.time()
    wide, rep = pull(box, "2003-01-01", "2024-12-31", VARS)
    res = engine.run(wide, names, max_lag=3, n_surrogates=500)
    print(f"\n==================== {label}  ({len(res['variables'])} variables, {len(res['pairs'])} pairs, {time.time()-t0:.0f}s)")
    p = res["pairs"]
    print(p[["a", "b", "best_lag", "r", "q", "partial_r", "partial_p", "granger_a_to_b_p", "granger_b_to_a_p", "surrogate_p", "level", "verdict"]]
          .to_string(index=False, float_format=lambda x: f"{x:.3g}"))
    pt = res["partial_trends"]
    sel = pt[(pt.p_alone < 0.05) & pt.physics_rule]
    print("\n-- trends vs their physical drivers (physics table)")
    print(sel[["y", "x", "trend_alone_per_decade", "p_alone", "trend_with_x_per_decade", "p_with_x", "x_effect_p", "share_of_trend_x_accounts_for", "verdict"]]
          .to_string(index=False, float_format=lambda x: f"{x:.3g}"))
    flip = pt[(pt.p_alone < 0.05) & (pt.verdict.str.startswith("Trend no longer"))]
    print("\n-- any variable whose trend disappears once another is accounted for")
    print(flip[["y", "x", "share_of_trend_x_accounts_for", "p_with_x", "x_effect_p", "physics_rule"]].to_string(index=False, float_format=lambda x: f"{x:.3g}") if len(flip) else "none")
