#!/usr/bin/env bash
# Build global cubes one after another; safe to rerun (downloads already on disk are skipped).
cd "$(dirname "$0")/.."
export PYTHONUNBUFFERED=1
.venv/bin/python -m earthpull.cubes aod_modis_aqua --start 2002-07-01 --end 2026-12-31 > data/cubes_aod.log 2>&1
.venv/bin/python -m earthpull.cubes air_temp aerosol wind_u850 wind_v850 --start 1980-01-01 --end 2025-12-31 > data/cubes_build.log 2>&1
