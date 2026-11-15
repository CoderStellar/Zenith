# Zenith: Earth System Trend Detective

NASA Space Apps Challenge 2026, "Be an Earth System Trend Detective". A tool that picks NASA Earth-science
variables for any region, builds the time series, measures the rate of change, tests whether it is significant,
finds which variables move together, and explains the results in plain language.

**Live site (static part):** https://coderstellar.github.io/Zenith/

## What is in this repo

| Folder | What it is |
|---|---|
| `Tool/` | The website: Pacific-states demo (Homepage, Map & States, About) and "Try it out yourself". Served by GitHub Pages and by the tool server. |
| `earthpull/` | The engine: NASA data access (earthaccess, Harmony, Giovanni averaging service), region averaging (boxes and outlines), trend tests, correlation engine, news lens, AI explanations, HTTP API, and the Streamlit workbench. |
| `scripts/` | Data builds for the site (`build_tool_data.py`), benchmarks against published studies (`benchmarks.py`), validation scripts. |
| `tests/` | Unit tests for the trend tests, correlation engine, regions and exports (`pytest`). |
| `reports/`, `research_notes/` | Research report on trend-analysis methods and its notes. |
| `deploy/`, `Dockerfile` | Container and Google Cloud deployment for the tool server. |

## Run it

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements.txt fastapi uvicorn geopandas regionmask pytest
.venv/bin/python -m earthpull login                  # NASA Earthdata login (free)
.venv/bin/uvicorn earthpull.api:app --port 8000      # site + API at http://localhost:8000
```

- The Homepage, Map & States and About tabs work as a static site (GitHub Pages).
- "Try it out yourself" needs the tool server above (it fetches NASA data on demand). Its plain-language
  explanations use an AI command-line tool configured on the server (see `earthpull/explain.py`); without it, template summaries are shown.
- Rebuild the demo data: `python scripts/build_tool_data.py fetch && python scripts/build_tool_data.py build && python scripts/build_tool_data.py grids`
- Tests: `.venv/bin/python -m pytest -q tests/`

## Methods in one paragraph

Values are monthly averages over a box or an outline (cells weighted by their share inside it and cos latitude).
The trend is a straight line fitted together with the seasonal cycle; its 95% range and p-value use an effective
sample size from the lag-1 autocorrelation (the adjustment IPCC AR6 uses). "Clear rise/fall" also needs a
Theil-Sen slope with the same correction to agree; otherwise "no clear trend yet". The correlation engine removes
seasons and trends, corrects for autocorrelation and multiple testing, runs surrogate and Granger checks, and only
calls a link "consistent with A influencing B" when a mechanism in a fixed physics table fits. Benchmarked against
9 published studies (13 of 16 checks pass); details in the site's About tab and `scripts/benchmarks.py`.

Built with NASA open data. Not affiliated with or endorsed by NASA.
