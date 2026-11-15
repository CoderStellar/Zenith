# West Coast Climate Assessment Tool

NASA Space Apps Challenge project ("Be an Earth System Trend Detective"). Measured trends, with significance tests,
for **Alaska, California, Hawaii, Oregon and Washington**, plus a "Try it out yourself" tab that runs the same engine
anywhere on Earth.

## Tabs
1. **Homepage**: real state-average trends (air temperature, precipitation, summer smoke, total water storage,
   soil moisture), each with a 95% range and a verdict; temperature anomalies 1980-2024; state comparison; change
   profile; seasonal precipitation.
2. **Try it out yourself**: pick any box and one or more NASA variables; get the trend, season and start-year
   checks, a per-grid-cell trend map, the correlation engine, and a plain-language explanation written by an AI model
   from the computed numbers (every number is checked against the results).
3. **Map & States**: choropleth of each state's trend, the West Coast analysis boxes and state bounding boxes,
   and per-grid-cell trend maps (air temperature, GRACE water storage).
4. **About**: methodology, correlation engine, benchmarks against 9 published studies, guardrails, sources.

## Data
`data.js` and `grids.js` are **real data**, generated from NASA datasets by the earthpull engine:

```bash
python scripts/build_tool_data.py fetch   # download (state outlines, cached)
python scripts/build_tool_data.py build   # statistics -> Tool/data.js
python scripts/build_tool_data.py grids   # per-cell trend maps -> Tool/grids.js
```

## Run locally
- Homepage, Map and About work as a static site: open `index.html`.
- "Try it out yourself" needs the tool server (NASA Earthdata login on the server; explanations use an AI
  command-line tool configured on the server):

```bash
.venv/bin/uvicorn earthpull.api:app --port 8000    # then open http://localhost:8000
```

## Files
- `index.html`: page structure and About content
- `styles.css`: styling
- `data.js`, `grids.js`: generated data (do not edit by hand)
- `app.js`: Homepage and Map tabs
- `try.js`: "Try it out yourself" tab (calls the tool server's `/api/*`)
