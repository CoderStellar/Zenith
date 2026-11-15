"""How many grid cells of each product fall in each US state (Census 2024 cartographic boundaries, 1:500k).
Fractional coverage via regionmask.mask_3D_frac_approx; 'effective cells' = sum of cell fractions."""
import warnings
import geopandas as gpd, numpy as np, pandas as pd, regionmask
warnings.filterwarnings("ignore")
states = gpd.read_file("zip://data/boundaries/cb_2024_us_state_500k.zip")
states = states[~states.STUSPS.isin(["PR", "VI", "GU", "MP", "AS"])].reset_index(drop=True)
regions = regionmask.from_geopandas(states, names="NAME", abbrevs="STUSPS", overlap=False)
print("states + DC:", len(states))
grids = {"MERRA-2 (0.5 x 0.625)": (0.5, 0.625), "GLDAS (0.25)": (0.25, 0.25), "IMERG (0.1)": (0.1, 0.1), "MODIS 08_M3 (1.0)": (1.0, 1.0)}
rows = {}
for gname, (dy, dx) in grids.items():
    # CONUS + AK + HI window, cell centres on each product's own lattice (MERRA-2: lat -90+k*0.5, lon -180+k*0.625)
    lat = np.arange(-90, 90 + 1e-9, dy) if "MERRA" in gname else np.arange(-90 + dy / 2, 90, dy)
    lon = np.arange(-180, 180, dx) if "MERRA" in gname else np.arange(-180 + dx / 2, 180, dx)
    lat = lat[(lat > 15) & (lat < 72)]; lon = lon[(lon > -180) & (lon < -64)]
    frac = regions.mask_3D_frac_approx(lon, lat)
    eff = frac.sum(("lat", "lon")).values
    centers = (frac > 0.5).sum(("lat", "lon")).values
    for ab, e, c in zip(frac.abbrevs.values, eff, centers):
        rows.setdefault(ab, {})[f"{gname} effective cells"] = round(float(e), 1)
df = pd.DataFrame(rows).T.sort_values("MERRA-2 (0.5 x 0.625) effective cells")
pd.set_option("display.width", 200)
print(df.head(12).to_string())
print("\nstates under 4 effective MERRA-2 cells:", ", ".join(df.index[df["MERRA-2 (0.5 x 0.625) effective cells"] < 4]))
print("states under 4 effective MODIS 1-degree cells:", ", ".join(df.index[df["MODIS 08_M3 (1.0) effective cells"] < 4]))
print("MD row:", df.loc["MD"].to_dict())
df.to_csv("data/boundaries/state_cell_counts.csv")
