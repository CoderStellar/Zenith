"""Outline (polygon) averaging, land masking and the self-describing CSV export."""
import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import box as sbox

from earthpull.core import BBox, _box_mean, _open_var, export_csv


def grid(values_inside=1.0, values_outside=0.0):
    lat = np.arange(30.25, 45, 0.5)
    lon = np.arange(-125.75, -110, 0.5)
    inside = (lon[None, :] > -121) & (lon[None, :] < -118) & (lat[:, None] > 35) & (lat[:, None] < 40)
    v = np.where(inside, values_inside, values_outside)[None].repeat(3, 0)
    return xr.DataArray(v, dims=("time", "lat", "lon"),
                        coords={"time": pd.date_range("2010-01-01", periods=3, freq="MS"), "lat": lat, "lon": lon})


def test_outline_average_is_not_diluted_by_the_surrounding_box():
    da = grid()
    big_box = BBox(-125, 31, -112, 43)
    poly = sbox(-121, 35, -118, 40)
    assert _box_mean(da, big_box)["value"].iloc[0] < 0.2  # rectangle mixes in the zeros around it
    assert abs(_box_mean(da, big_box, poly)["value"].iloc[0] - 1.0) < 0.05


def test_outline_smaller_than_a_cell_uses_the_cell_at_its_centre():
    da = grid()
    tiny = sbox(-119.6, 37.6, -119.5, 37.7)
    assert abs(_box_mean(da, BBox(-119.6, 37.6, -119.5, 37.7), tiny)["value"].iloc[0] - 1.0) < 1e-9


def test_land_mask_drops_ocean_cells(tmp_path):
    da = grid(values_inside=-10.0, values_outside=0.0)  # "land" depleting, "ocean" flat
    mask = xr.DataArray((da.isel(time=0) != 0).astype(int).values, dims=("lat", "lon"),
                        coords={"lat": da.lat, "lon": da.lon})
    f = tmp_path / "grace_like.nc"
    xr.Dataset({"lwe_thickness": da, "land_mask": mask}).to_netcdf(f)
    b = BBox(-122, 34, -117, 41)
    raw = _box_mean(_open_var(f, "lwe_thickness"), b)["value"].iloc[0]
    masked = _box_mean(_open_var(f, "lwe_thickness", "land_mask"), b)["value"].iloc[0]
    assert raw > -9.0 and abs(masked + 10.0) < 1e-9


def test_csv_export_names_units_and_sources():
    wide = pd.DataFrame({"water_storage": [1.0, 2.0], "precip": [0.1, 0.2]},
                        index=pd.PeriodIndex(["2010-01", "2010-02"], freq="M"))
    rep = pd.DataFrame([{"id": "water_storage", "units": "cm", "via": "download", "region": "outline"},
                        {"id": "precip", "units": "mm/hr", "via": "harmony", "region": "outline"}])
    text = export_csv(wide, rep, "Central Valley (uploaded outline)", "2010-01-01", "2010-02-28")
    assert "water_storage [cm]" in text and "precip [mm/hr]" in text
    assert "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4" in text and "GPM_3IMERGM v07" in text
    assert "Central Valley" in text
