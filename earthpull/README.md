# earthpull

Give it a bounding box. It tells you which NASA variables have data there, pulls them,
area-averages each one over the box, and writes one monthly table ready for trend analysis.

## Setup (once)

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv earthaccess harmony-py xarray netCDF4 h5netcdf pandas pyarrow pyyaml dask pyhdf
.venv/bin/python -m earthpull login      # your Earthdata username/password (same as Giovanni)
```

Then in https://urs.earthdata.nasa.gov > Applications > Authorized Apps, approve
**NASA GESDISC DATA ARCHIVE**, **LP DAAC Data Pool** and **PO.DAAC**. Downloads fail with 401 until you do.

## Use

```bash
# what exists for this box (metadata only, seconds)
.venv/bin/python -m earthpull check --bbox 70,24,90,32 --start 2003-01-01 --end 2024-12-31

# pull everything monthly -> data/out/box_....csv/.parquet + _report.csv
.venv/bin/python -m earthpull pull --bbox 70,24,90,32 --start 2003-01-01 --end 2024-12-31

# just some variables
.venv/bin/python -m earthpull pull --bbox 70,24,90,32 --only air_temp,precip,water_storage

# confirm variable names in a real file before trusting sources.yaml
.venv/bin/python -m earthpull inspect precip
```

Output table: one row per month, one column per variable id. Months where less than 70% of
the box has valid data are blanked (`--min-valid`). The report CSV gives units, months and
coverage per variable.

## How each source is fetched

| Method | Sources | What happens | 22 years for one box |
|---|---|---|---|
| Giovanni | IMERG, GLDAS (2), AIRS, OMI | Giovanni's area-averaging engine via Harmony returns the box-mean series as one CSV. Same numbers as Giovanni's website (checked: matches our own averaging to 1e-7). | 20 s to 2 min |
| Harmony subset | MERRA-2 T2M and aerosol | NASA cuts each monthly file to the box; we average locally. Giovanni's service does not accept these MERRA-2 IDs. | about 10 min |
| Download | MODIS NDVI and LST, GRACE | Whole global files (no Harmony service), cached in `data/raw/_global`, reused for every box. | MODIS about 40 GB; GRACE one 46 MB file |

If the Giovanni service fails, the tool falls back to Harmony subsetting automatically. Dates are clipped to each
product's own record (OMI starts 2004-10, IMERG V07 ends 2025-09 in the catalog).

## Test results (Northern India box 70,24,90,32)

| Variable | Status |
|---|---|
| MERRA-2 air temp, aerosol | works (Harmony) |
| IMERG precip, GLDAS soil moisture and evaporation, AIRS air temp, OMI NO2 | works (Giovanni) |
| GRACE water storage | works (231 months 2003-2024; gaps are real mission gaps) |
| MODIS NDVI and LST | works for test months; full record is a large download |

Other challenge resources: Giovanni website up; KNMI Climate Explorer up; AppEEARS API up (193 products, has
MOD13A3 monthly NDVI, not MOD13C2); NOAA CDO API needs a free token; GES DISC Hydrology Data Rods service is
discontinued (redirects to a retirement notice).

## UI

```bash
.venv/bin/streamlit run earthpull/main.py
```
Draw a box, type coordinates, or give a point and radius. It lists what exists there, then pulls and plots.

## Known limits
- Boxes cannot cross the 180° line.
- A box smaller than one grid cell of a product fails for that product (GRACE cells are 0.5° but the real resolution is about 3°).
- Giovanni-method series have no valid-fraction column, so the 70% coverage filter only applies to Harmony and download sources.
- Variable names in `sources.yaml` were confirmed against real files on 2026-11-14.

## Global trend maps

```bash
.venv/bin/python -m earthpull.trendmap --var water_storage --res 1.0     # local test, ~90 s
```
Per grid cell: monthly anomalies, Sen slope per decade, Mann-Kendall (Hamed-Rao), OLS t-test,
Benjamini-Hochberg FDR across cells. Writes `data/trendmaps/<var>_<start>_<end>.nc` and a `.png` map
(red/blue = clear trend, grey = no clear change yet). Cells need 10 years of data.

## Google Cloud

`deploy/gcp.sh` (same container for the UI and the batch job; data cache in a GCS bucket mounted at /data):

```bash
gcloud auth login && gcloud config set project <project-id>
deploy/gcp.sh setup       # APIs, bucket, Earthdata secrets (prompts), image
deploy/gcp.sh ui          # public Streamlit URL on Cloud Run
deploy/gcp.sh trendmaps   # 9 variables in parallel, 8 vCPU / 32 GB each
deploy/gcp.sh results     # copy maps back to data/trendmaps
```
