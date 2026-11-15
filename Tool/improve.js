/* improve.js - accessibility, data tables, scope panel and the 2050 projection.
   Loaded after app.js (which exposes window.VIZ). All maths is plain JavaScript: no libraries. */
(function () {
  "use strict";
  var V = window.VIZ;
  if (!V || !window.Chart) return;
  var STATS = window.STATS, TREND = window.TREND, SEASONAL = window.SEASONAL, META = window.META || {};
  var names = V.names, VARS = V.VARS, keys = V.keys, palette = V.palette;
  var HORIZON = 2050;
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var sgn = function (x, d) { return (x == null || isNaN(x)) ? "n/a" : (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(d == null ? 2 : d); };
  var mean = function (a) { var s = 0; for (var i = 0; i < a.length; i++) s += a[i]; return s / a.length; };
  var hexA = function (h, a) { var n = parseInt(h.slice(1), 16); return "rgba(" + (n >> 16) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")"; };
  var MARKS = { Alaska: "circle", California: "triangle", Hawaii: "rect", Oregon: "rectRot", Washington: "crossRot" };
  var DASH = { Alaska: [], California: [9, 4], Hawaii: [2, 3], Oregon: [10, 3, 2, 3], Washington: [4, 4] };

  /* ================= Statistics (no libraries) ================= */
  function lgamma(z) {
    var c = [76.18009172947146, -86.50532032941677, 24.01409824083091, -1.231739572450155, 0.1208650973866179e-2, -0.5395239384953e-5];
    var x = z, y = z, tmp = x + 5.5, ser = 1.000000000190015;
    tmp -= (x + 0.5) * Math.log(tmp);
    for (var j = 0; j < 6; j++) ser += c[j] / ++y;
    return -tmp + Math.log(2.5066282746310005 * ser / x);
  }
  function betacf(a, b, x) {
    var FP = 1e-300, qab = a + b, qap = a + 1, qam = a - 1, c = 1, d = 1 - qab * x / qap;
    if (Math.abs(d) < FP) d = FP; d = 1 / d; var h = d;
    for (var m = 1; m <= 300; m++) {
      var m2 = 2 * m, aa = m * (b - m) * x / ((qam + m2) * (a + m2));
      d = 1 + aa * d; if (Math.abs(d) < FP) d = FP; c = 1 + aa / c; if (Math.abs(c) < FP) c = FP; d = 1 / d; h *= d * c;
      aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2));
      d = 1 + aa * d; if (Math.abs(d) < FP) d = FP; c = 1 + aa / c; if (Math.abs(c) < FP) c = FP; d = 1 / d;
      var del = d * c; h *= del; if (Math.abs(del - 1) < 3e-12) break;
    }
    return h;
  }
  function ibeta(x, a, b) {  // regularised incomplete beta function
    if (x <= 0) return 0; if (x >= 1) return 1;
    var bt = Math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log(1 - x));
    return x < (a + 1) / (a + b + 2) ? bt * betacf(a, b, x) / a : 1 - bt * betacf(b, a, 1 - x) / b;
  }
  function tcdf(t, df) { var p = 0.5 * ibeta(df / (df + t * t), df / 2, 0.5); return t > 0 ? 1 - p : p; }
  function tinv(p, df) {  // inverse of Student's t CDF for p in (0.5, 1), by bisection
    var lo = 0, hi = 1; while (tcdf(hi, df) < p && hi < 1e7) hi *= 2;
    for (var i = 0; i < 200; i++) { var mid = (lo + hi) / 2; if (tcdf(mid, df) < p) lo = mid; else hi = mid; }
    return (lo + hi) / 2;
  }
  /* Ordinary least squares with an autocorrelation-adjusted effective sample size
     (lag-1 autocorrelation of the residuals, Santer et al. 2008 / IPCC AR6), the same correction
     the site's trend test uses. lineHalf(x0): 95% half-width for the fitted line at x0.
     predHalf(x0): 95% half-width for one new observation at x0 (adds the scatter sigma^2). */
  function ols(x, y) {
    var n = x.length, xb = mean(x), yb = mean(y), sxx = 0, sxy = 0, i;
    for (i = 0; i < n; i++) { sxx += (x[i] - xb) * (x[i] - xb); sxy += (x[i] - xb) * (y[i] - yb); }
    var b = sxy / sxx, a = yb - b * xb, e = [], sse = 0;
    for (i = 0; i < n; i++) { e.push(y[i] - (a + b * x[i])); sse += e[i] * e[i]; }
    var s2 = sse / (n - 2), num = 0;
    for (i = 1; i < n; i++) num += e[i] * e[i - 1];
    var r1 = sse > 0 ? num / sse : 0;
    var neff = r1 > 0 ? Math.min(n, Math.max(4, n * (1 - r1) / (1 + r1))) : n;
    var infl = (n - 2) / (neff - 2), dof = neff - 2, t = tinv(0.975, dof);
    var varLine = function (x0) { return s2 * infl * (1 / n + (x0 - xb) * (x0 - xb) / sxx); };
    return { n: n, xb: xb, yb: yb, a: a, b: b, sxx: sxx, s2: s2, r1: r1, neff: neff, dof: dof, t: t,
      slopeHalf: t * Math.sqrt(s2 * infl / sxx),
      lineHalf: function (x0) { return t * Math.sqrt(varLine(x0)); },
      predHalf: function (x0) { return t * Math.sqrt(s2 + varLine(x0)); } };
  }
  window.VIZ_SELFTEST = function () {  // run in the browser console: VIZ_SELFTEST()
    var near = function (a, b, tol) { return Math.abs(a - b) <= tol; };
    var f = ols([1, 2, 3, 4, 5], [2, 4, 5, 4, 5]);
    var out = {
      t975_df5: [tinv(0.975, 5), 2.5706, near(tinv(0.975, 5), 2.5706, 5e-4)],
      t975_df10: [tinv(0.975, 10), 2.2281, near(tinv(0.975, 10), 2.2281, 5e-4)],
      t975_df30: [tinv(0.975, 30), 2.0423, near(tinv(0.975, 30), 2.0423, 5e-4)],
      t975_df43: [tinv(0.975, 43), 2.0167, near(tinv(0.975, 43), 2.0167, 5e-4)],
      ols_slope: [f.b, 0.6, near(f.b, 0.6, 1e-12)], ols_intercept: [f.a, 2.2, near(f.a, 2.2, 1e-12)], ols_sigma2: [f.s2, 0.8, near(f.s2, 0.8, 1e-12)]
    };
    names.forEach(function (s) {
      var m = TREND.series[s], g = ols(TREND.years, m), pub = STATS[s].temp.slope_per_decade;
      out["temp_" + s + "_annual_vs_monthly"] = [+(g.b * 10).toFixed(3), pub, near(g.b * 10, pub, 0.08)];
    });
    return out;
  };

  /* ================= Projection model ================= */
  var UNIT = { temp: "°C", precip: "% of average", smoke: "AOD", water: "mm of water", soil: "% of average" };
  var PER = { temp: 0.1, precip: 0.1, smoke: 0.1, water: 1, soil: 0.1 };  // published slopes are per decade, except water (per year)
  function recordYears(rec) { var m = /(\d{4})\D+(\d{4})/.exec(String(rec || "")); return m ? [+m[1], +m[2]] : null; }
  function yearly(k, s) {  // yearly values the site holds: temperature (yearly means) and summer smoke
    if (k === "temp" && TREND && TREND.series && TREND.series[s]) {
      return { x: TREND.years.slice(), y: TREND.series[s].slice() };
    }
    if (k === "smoke" && STATS[s].smoke && STATS[s].smoke.by_year) {
      var by = STATS[s].smoke.by_year, ys = Object.keys(by).map(Number).sort(function (a, b) { return a - b; });
      return { x: ys, y: ys.map(function (yr) { return by[yr]; }) };
    }
    return null;
  }
  function model(k, s) {
    var p = VARS[k].pick(s);
    if (!p || p.v == null || isNaN(p.v) || p.lo == null || p.hi == null) return null;
    var rec = recordYears(STATS[s][k].record); if (!rec) return null;
    var ser = yearly(k, s), m = { k: k, s: s, pub: p, unit: UNIT[k], per: PER[k], ser: ser, y0: rec[0], y1: rec[1] };
    if (ser && ser.x.length >= 8) {
      var f = ols(ser.x, ser.y);
      m.fit = f; m.y0 = ser.x[0]; m.y1 = ser.x[ser.x.length - 1]; m.xbar = f.xb; m.slope = f.b; m.hw = f.slopeHalf;
      m.level = function (t) { var c = f.a + f.b * t, h = f.lineHalf(t), q = f.predHalf(t); return { c: c, lo: c - h, hi: c + h, plo: c - q, phi: c + q }; };
    } else {  // only the published trend and its 95% range are available: the line is the change from the record's average
      m.xbar = (rec[0] + rec[1]) / 2; m.slope = p.v * PER[k]; m.hw = (p.hi - p.lo) / 2 * PER[k];
      m.level = function (t) { var c = m.slope * (t - m.xbar), h = m.hw * Math.abs(t - m.xbar); return { c: c, lo: c - h, hi: c + h }; };
    }
    m.delta = function (t) { var c = m.slope * (t - m.xbar), h = m.hw * Math.abs(t - m.xbar); return { c: c, lo: c - h, hi: c + h }; };
    return m;
  }
  var perText = function (k) { return PER[k] === 1 ? "per year" : "per decade"; };
  var yTitle = function (m) { return m.fit ? (m.k === "temp" ? "°C relative to the " + TREND.baseline + " average" : "aerosol optical depth (AOD, no unit)") : "change from the record’s average, " + m.unit; };

  /* ================= Accessibility helpers ================= */
  function table(caption, head, rows) {
    return '<table class="dtable"><caption>' + esc(caption) + '</caption><thead><tr>' + head.map(function (h) { return '<th scope="col">' + esc(h) + '</th>'; }).join("") +
      '</tr></thead><tbody>' + rows.map(function (r) { return '<tr><th scope="row">' + esc(r[0]) + '</th>' + r.slice(1).map(function (c) { return '<td>' + esc(c) + '</td>'; }).join("") + '</tr>'; }).join("") + '</tbody></table>';
  }
  function describe(canvasId, label, summaryText) {
    var c = $(canvasId); if (!c) return;
    var box = c.parentNode, p = $(canvasId + "-desc");
    if (!p) { p = document.createElement("p"); p.id = canvasId + "-desc"; p.className = "sr-only"; box.appendChild(p); }
    p.textContent = summaryText;
    c.setAttribute("role", "img"); c.setAttribute("aria-label", label); c.setAttribute("aria-describedby", p.id);
  }
  function dataTable(canvasId, html) {  // collapsible real table under a chart
    var c = $(canvasId), id = canvasId + "-table", t = $(id);
    if (!t) {
      var host = c.closest(".chart-box"); if (!host) return;
      host.insertAdjacentHTML("afterend", '<details class="viewdata"><summary>View this chart as a table</summary><div class="scroll tablebox" id="' + id + '"></div></details>');
      t = $(id);
    }
    t.innerHTML = html;
  }
  window.vizPattern = function (color) {  // diagonal hatch = "no clear trend yet" (shape, not only colour)
    var c = document.createElement("canvas"); c.width = c.height = 8;
    var x = c.getContext("2d"); x.strokeStyle = color; x.lineWidth = 2; x.beginPath();
    x.moveTo(0, 8); x.lineTo(8, 0); x.moveTo(-2, 2); x.lineTo(2, -2); x.moveTo(6, 10); x.lineTo(10, 6); x.stroke();
    return x.createPattern(c, "repeat");
  };
  function lineStyle(id, pts) {  // marker shape + dash style per state, so lines differ without colour
    var ch = Chart.getChart(id); if (!ch) return;
    ch.data.datasets.forEach(function (d) {
      var s = d.label; d.borderColor = palette[s]; d.backgroundColor = palette[s]; d.borderDash = DASH[s] || []; d.borderWidth = 2.5;
      d.pointStyle = MARKS[s] || "circle"; d.pointHoverRadius = 6;
      d.pointRadius = pts ? function (c) { return c.dataIndex % 5 === 0 ? 4 : 0; } : 4;
    });
    ch.options.plugins.legend.labels = { usePointStyle: true, boxWidth: 9, padding: 14, font: { size: 13 } };
    ch.update();
  }

  /* ================= Existing charts: text alternatives, tables, styles ================= */
  Chart.defaults.font.size = 13;
  var trendSentence = function () { return names.map(function (s) { var p = VARS.temp.pick(s); return s + " " + sgn(p.v) + " °C per decade (" + p.verdict + ")"; }).join("; "); };
  describe("chart-trend", "Line chart: yearly air temperature anomaly, " + TREND.years[0] + " to " + TREND.years[TREND.years.length - 1] + ", five states",
    "Yearly state-average air temperature compared with the " + TREND.baseline + " average. Trend per decade: " + trendSentence() + ". A table of every value follows the chart.");
  dataTable("chart-trend", table("Yearly air temperature anomaly, °C relative to the " + TREND.baseline + " average", ["Year"].concat(names),
    TREND.years.map(function (y, i) { return [String(y)].concat(names.map(function (s) { return sgn(TREND.series[s][i]); })); })));
  lineStyle("chart-trend", true);

  var barKey = function () { return $("home-var").value; };
  function refreshBar() {
    var k = barKey(), v = VARS[k];
    describe("chart-bar", "Bar chart: " + v.label + " in each state with its 95% range",
      v.label + " by state, in " + v.unit + ": " + names.map(function (s) { var p = v.pick(s); return s + " " + sgn(p.v, 3) + " (" + p.verdict + ")"; }).join("; ") + ".");
    dataTable("chart-bar", table(v.label + " (" + v.unit + ")", ["State", "Trend", "95% low", "95% high", "Verdict"],
      names.map(function (s) { var p = v.pick(s); return [s, sgn(p.v, 3), sgn(p.lo, 3), sgn(p.hi, 3), p.verdict || ""]; })));
  }
  $("home-var").addEventListener("change", refreshBar); refreshBar();
  if ($("bar-note")) $("bar-note").setAttribute("aria-live", "polite");
  $("home-var").dispatchEvent(new Event("change"));   // redraw with hatch patterns
  var homeBar = Chart.getChart("chart-bar");  // make the 95% range bars readable on the dark background
  if (homeBar) { homeBar.data.datasets[1].backgroundColor = "rgba(241,243,245,0.3)"; homeBar.data.datasets[1].borderColor = "#f1f3f5"; homeBar.update(); }

  describe("chart-season", "Line chart: average precipitation in each month, five states",
    "Monthly average precipitation in millimetres, state averages. " + names.map(function (s) {
      var a = SEASONAL.series[s], hi = a.indexOf(Math.max.apply(null, a)); return s + " is wettest in " + SEASONAL.months[hi] + " (" + a[hi].toFixed(0) + " mm)"; }).join("; ") + ". A table of every value follows the chart.");
  dataTable("chart-season", table("Average precipitation, mm per month", ["Month"].concat(names),
    SEASONAL.months.map(function (m, i) { return [m].concat(names.map(function (s) { return SEASONAL.series[s][i].toFixed(1); })); })));
  lineStyle("chart-season", false);

  function refreshRadar() {
    var s = $("home-state").value;
    describe("chart-radar", "Radar chart: how " + s + " ranks among the five states on each variable",
      "Each axis ranks " + s + "’s trend from lowest (centre) to highest (edge) among the five states. Exact values: " +
      keys.map(function (k) { var p = VARS[k].pick(s); return VARS[k].label.replace(" trend", "") + " " + sgn(p.v) + " " + VARS[k].unit + " (" + p.verdict + ")"; }).join("; ") + ".");
    dataTable("chart-radar", table("Trends in " + s, ["Variable", "Trend", "Unit", "Verdict"],
      keys.map(function (k) { var p = VARS[k].pick(s); return [VARS[k].label.replace(" trend", ""), sgn(p.v, 3), VARS[k].unit, p.verdict || ""]; })));
  }
  $("home-state").addEventListener("change", refreshRadar); refreshRadar();

  if ($("cmp-pair") && META.compare) {
    var refreshCmp = function () {
      var c = META.compare[$("cmp-pair").value]; if (!c) return;
      describe("chart-cmp", "Bar chart: correlation between two variables in each state",
        "Correlation r after seasons and trends are removed, from -1 to 1: " + c.rows.map(function (r) { return r.place + " " + (r.r == null ? "n/a" : sgn(r.r)) + " (" + r.verdict + ")"; }).join("; ") + ".");
      dataTable("chart-cmp", table("Correlation by state", ["State", "r", "Delay (months)", "Verdict"],
        c.rows.map(function (r) { return [r.place, r.r == null ? "n/a" : sgn(r.r), String(r.best_lag), r.verdict]; })));
    };
    $("cmp-pair").addEventListener("change", refreshCmp); refreshCmp(); $("cmp-pair").dispatchEvent(new Event("change"));
  }
  Object.keys(Chart.instances).forEach(function (id) { Chart.instances[id].update(); });

  /* ================= Scope and plain-language guide ================= */
  var kpis = $("kpis");
  if (kpis && !$("scope")) kpis.insertAdjacentHTML("beforebegin",
    '<section id="scope" class="scope" aria-labelledby="scope-h"><h2 id="scope-h" class="sr-only">Scope of this tool</h2>' +
    '<article class="card"><h3>Current scope</h3><ul>' +
    '<li><strong>Places:</strong> Alaska, California, Hawaii, Oregon and Washington (state averages), plus any box on Earth in &ldquo;Try it out yourself&rdquo;.</li>' +
    '<li><strong>Measured variables:</strong> air temperature (MERRA-2, 1980&ndash;2024), precipitation (GPM IMERG, 2001&ndash;2024), summer smoke and haze (MODIS Aqua, 2003&ndash;2024), total water storage (GRACE/GRACE-FO, 2003&ndash;2024) and soil moisture (GLDAS Noah, 2003&ndash;2024).</li>' +
    '<li><strong>What you get:</strong> each trend with a 95% range and a significance verdict, links between variables, and straight-line projections to 2050.</li></ul></article>' +
    '<article class="card"><h3>Not covered</h3><ul>' +
    '<li>Why something changes: the tool reports links, never causes.</li>' +
    '<li>Climate-model or emissions-scenario forecasts. The 2050 view only extends each measured trend.</li>' +
    '<li>Anything smaller than a state, single events (a storm, one fire) or real-time conditions.</li>' +
    '<li>Health, economic or planning advice.</li></ul></article>' +
    '<article class="card"><h3>Future scope <span class="tag">proposed, not built</span></h3><ul>' +
    '<li>More regions and finer areas.</li><li>Scenario-based projections from climate-model ensembles (for example CMIP6).</li>' +
    '<li>More variables, such as sea level and extreme events.</li><li>Data download and a public API.</li></ul></article>' +
    '<article class="card"><h3>How to read this</h3><dl class="glossary">' +
    '<dt>Trend</dt><dd>How fast a variable changes, in the unit shown per decade (or per year for water).</dd>' +
    '<dt>95% range</dt><dd>The range the true trend most likely lies in. If it includes zero, the verdict is &ldquo;no clear trend yet&rdquo;.</dd>' +
    '<dt>Anomaly</dt><dd>The difference from an average (here ' + esc(TREND.baseline) + '). &deg;C differences equal kelvin differences.</dd>' +
    '<dt>AOD</dt><dd>Aerosol optical depth: how hazy the air is. It has no unit.</dd>' +
    '<dt>Units</dt><dd>SI: &deg;C, millimetres of water (1 mm = 1 kg per m&sup2;), km&sup3;, per decade or year.</dd></dl></article></section>');

  /* ================= Projection section ================= */
  var anchor = document.querySelector("#panel-home .hero.slim");
  if (anchor && !$("projection")) anchor.insertAdjacentHTML("beforebegin",
    '<section id="projection" aria-labelledby="proj-h">' +
    '<div class="hero slim"><h2 id="proj-h">Where do the trends lead by 2050?</h2>' +
    '<p class="sub">Each measured trend extended in a straight line to 2050, with its 95% uncertainty. This is a statistical projection, not a climate-model forecast: it assumes the trend seen so far simply continues.</p></div>' +
    '<div class="card detailbar projbar"><label class="inline">Variable <select id="proj-var"></select></label>' +
    '<label class="inline">State <select id="proj-state"></select></label>' +
    '<button type="button" id="proj-csv" class="ghost">Download CSV</button></div>' +
    '<div class="grid two">' +
    '<article class="card"><h3>Trend line to 2050</h3><p class="sub" id="proj-axis"></p>' +
    '<div class="chart-box tall"><canvas id="chart-proj"></canvas></div><ul class="profile" id="proj-facts" aria-live="polite"></ul></article>' +
    '<article class="card"><h3>Projected change by 2050, all states</h3>' +
    '<p class="sub" id="proj-bar-sub"></p><div class="chart-box tall"><canvas id="chart-proj-bar"></canvas></div>' +
    '<p class="sub">Solid bars: clear trend. Hatched bars: no clear trend yet. Thin bar: 95% range of the trend line.</p></article></div>' +
    '<article class="card explain"><h3>How this is calculated</h3><ol class="method">' +
    '<li><strong>Straight-line fit.</strong> Temperature and summer smoke use ordinary least squares on the yearly values shown. Precipitation, soil moisture and water storage use the published trend and its 95% range (the site holds their monthly trend statistics, not yearly values).</li>' +
    '<li><strong>Uncertainty grows with distance.</strong> The 95% range of the trend line is slope range &times; distance from the centre of the record, so it is narrowest mid-record and widest in 2050. Student&rsquo;s t is used, with an effective sample size from the lag-1 autocorrelation of the residuals (Santer et al. 2008), the same correction as the site&rsquo;s trend test.</li>' +
    '<li><strong>One year versus the trend.</strong> Where yearly values exist, a second band adds the year-to-year scatter: the range a single future year could fall in (95% prediction interval).</li>' +
    '<li><strong>What it leaves out.</strong> Changes in the trend itself, feedbacks, emissions choices, volcanic or El Ni&ntilde;o effects and physical limits (for example, glaciers cannot lose more water than they hold). Treat 2050 values as &ldquo;if nothing changes about the trend&rdquo;.</li>' +
    '<li><strong>Units.</strong> SI: &deg;C, millimetres of water, and percent of the record&rsquo;s average.</li></ol></article></section>');
  if (!$("projection")) return;

  var pv = $("proj-var"), ps = $("proj-state");
  pv.innerHTML = keys.map(function (k) { return '<option value="' + k + '">' + esc(VARS[k].label.replace(" trend", "")) + '</option>'; }).join("");
  ps.innerHTML = names.map(function (s) { return '<option value="' + s + '">' + esc(s) + '</option>'; }).join("");
  var projChart = null, projBar = null, lastModel = null;
  var span = function (a, b, fn) { var o = []; for (var t = a; t <= b; t++) o.push({ x: t, y: fn(t) }); return o; };
  var verdictHtml = function (p) { return V.badge(p.verdict); };

  function drawLine(m, k, s) {
    var color = palette[s], ds = [];
    if (m.ser) ds.push({ label: "Observed yearly values", data: m.ser.x.map(function (x, i) { return { x: x, y: m.ser.y[i] }; }), showLine: false, pointRadius: 3, pointStyle: "circle", backgroundColor: "#b9c1c8", borderColor: "#b9c1c8" });
    ds.push({ label: "Fitted trend over the record", data: span(m.y0, m.y1, function (t) { return m.level(t).c; }), borderColor: color, backgroundColor: color, borderWidth: 3, pointRadius: 0 });
    ds.push({ label: "Projection if the trend continues", data: span(m.y1, HORIZON, function (t) { return m.level(t).c; }), borderColor: color, backgroundColor: color, borderWidth: 3, borderDash: [9, 5], pointRadius: 0 });
    if (m.fit) {
      ds.push({ label: "upper single-year", noLegend: true, data: span(m.y1, HORIZON, function (t) { return m.level(t).phi; }), borderColor: hexA(color, 0.55), borderDash: [2, 3], borderWidth: 1, pointRadius: 0, fill: false });
      ds.push({ label: "95% range for a single year", data: span(m.y1, HORIZON, function (t) { return m.level(t).plo; }), borderColor: hexA(color, 0.55), backgroundColor: hexA(color, 0.1), borderDash: [2, 3], borderWidth: 1, pointRadius: 0, fill: "-1" });
    }
    ds.push({ label: "upper trend line", noLegend: true, data: span(m.y0, HORIZON, function (t) { return m.level(t).hi; }), borderColor: "transparent", pointRadius: 0, fill: false });
    ds.push({ label: "95% range of the trend line", data: span(m.y0, HORIZON, function (t) { return m.level(t).lo; }), borderColor: "transparent", backgroundColor: hexA(color, 0.3), pointRadius: 0, fill: "-1" });
    if (!projChart) {
      projChart = new Chart($("chart-proj"), { type: "line", data: { datasets: ds }, options: {
        interaction: { mode: "nearest", axis: "x", intersect: false },
        plugins: { legend: { position: "bottom", labels: { filter: function (it, d) { return !d.datasets[it.datasetIndex].noLegend; }, boxWidth: 14, font: { size: 12 } } },
                   tooltip: { filter: function (it) { return !it.dataset.noLegend; }, callbacks: { label: function (c) { return c.dataset.label + ": " + sgn(c.parsed.y) + " " + (c.dataset.unit || ""); } } } },
        scales: { x: { type: "linear", ticks: { callback: function (v) { return String(v); }, maxTicksLimit: 9 } }, y: { title: { display: true, text: "" } } } } });
    }
    ds.forEach(function (d) { d.unit = m.unit; });
    projChart.data.datasets = ds;
    projChart.options.scales.x.min = m.y0; projChart.options.scales.x.max = HORIZON;
    projChart.options.scales.y.title.text = yTitle(m);
    projChart.update();
  }

  function facts(m, k, s) {
    var u = m.unit, perD = m.slope / m.per, h = m.hw / m.per, L = [];
    var at = m.level(HORIZON), dl = m.delta(HORIZON);
    L.push("<li><span>Trend used</span> <strong>" + sgn(perD, 3) + " " + esc(u) + " " + perText(k) + "</strong> <span class=\"sub\">(95% range " + sgn(perD - h, 3) + " to " + sgn(perD + h, 3) + ")</span> " + verdictHtml(m.pub) + "</li>");
    if (m.fit) {
      L.push("<li><span>In " + HORIZON + "</span> <strong>" + sgn(at.c) + " " + esc(k === "temp" ? "°C vs the " + TREND.baseline + " average" : u) + "</strong> <span class=\"sub\">trend line 95% range " + sgn(at.lo) + " to " + sgn(at.hi) + "; a single year " + sgn(at.plo) + " to " + sgn(at.phi) + "</span></li>");
      L.push("<li><span>Cross-check</span> <span class=\"sub\">slope from yearly values " + sgn(m.fit.b * 10, 3) + " " + esc(VARS[k].unit) + "; published slope from monthly data " + sgn(m.pub.v, 3) + ". Effective sample size " + m.fit.neff.toFixed(0) + " of " + m.fit.n + " years.</span></li>");
    } else {
      L.push("<li><span>Change by " + HORIZON + "</span> <strong>" + sgn(dl.c, 1) + " " + esc(u) + "</strong> <span class=\"sub\">relative to the record’s average; trend line 95% range " + sgn(dl.lo, 1) + " to " + sgn(dl.hi, 1) + "</span></li>");
    }
    if (dl.lo < 0 && dl.hi > 0) L.push("<li><span class=\"sub\">The range includes zero, so the data do not yet rule out no change, or a change in the opposite direction.</span></li>");
    return L.join("");
  }

  function drawBar(k) {
    var rows = names.map(function (s) { var m = model(k, s); return m ? { s: s, d: m.delta(HORIZON), p: m.pub } : { s: s, d: null, p: null }; });
    var u = UNIT[k];
    if (!projBar) {
      projBar = new Chart($("chart-proj-bar"), { type: "bar", data: { labels: names, datasets: [
        { label: "change by 2050", data: [], backgroundColor: [], borderColor: [], borderWidth: 1.5, order: 2 },
        { label: "95% range", data: [], backgroundColor: "rgba(241,243,245,0.35)", borderColor: "#f1f3f5", borderWidth: 1, barPercentage: 0.18, grouped: false, order: 1 }] },
        options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (c) {
          var r = rows[c.dataIndex]; if (!r.d) return "Not measured for this state";
          return [sgn(r.d.c, 1) + " " + u + " by " + HORIZON, "95% range " + sgn(r.d.lo, 1) + " to " + sgn(r.d.hi, 1), r.p.verdict]; } } } }, scales: { y: { title: { display: true, text: "" } } } } });
    }
    var d0 = projBar.data.datasets[0], d1 = projBar.data.datasets[1];
    d0.data = rows.map(function (r) { return r.d ? r.d.c : null; });
    d0.backgroundColor = rows.map(function (r) { return r.d && V.clear(r.p.verdict) ? palette[r.s] : window.vizPattern(palette[r.s]); });
    d0.borderColor = rows.map(function (r) { return palette[r.s]; });
    d1.data = rows.map(function (r) { return r.d ? [r.d.lo, r.d.hi] : null; });
    projBar.options.scales.y.title.text = "change by " + HORIZON + ", " + u;
    projBar.update();
    $("proj-bar-sub").textContent = "Change from each record’s average level to " + HORIZON + " if its straight-line trend continues, in " + u + ".";
    var sum = VARS[k].label.replace(" trend", "") + ", projected change by " + HORIZON + " in " + u + ": " + rows.map(function (r) { return r.d ? r.s + " " + sgn(r.d.c, 1) + " (" + r.p.verdict + ")" : r.s + " not measured"; }).join("; ") + ".";
    describe("chart-proj-bar", "Bar chart: projected change by " + HORIZON + " in each state", sum);
    dataTable("chart-proj-bar", table("Projected change by " + HORIZON + " (" + u + ")", ["State", "Change", "95% low", "95% high", "Verdict"],
      rows.map(function (r) { return r.d ? [r.s, sgn(r.d.c, 1), sgn(r.d.lo, 1), sgn(r.d.hi, 1), r.p.verdict || ""] : [r.s, "not measured", "", "", ""]; })));
  }

  function drawAll() {
    var k = pv.value, s = ps.value, m = model(k, s); lastModel = m;
    drawBar(k);
    var facts_ = $("proj-facts");
    if (!m) {
      if (projChart) { projChart.data.datasets = []; projChart.update(); }
      facts_.innerHTML = "<li><span class=\"sub\">" + esc(STATS[s][k].verdict || "No data") + ". No projection is shown.</span></li>";
      $("proj-axis").textContent = "No projection for " + s + ".";
      describe("chart-proj", "Trend line to " + HORIZON + " (not available)", "No projection for " + s + ": " + (STATS[s][k].verdict || "no data") + ".");
      dataTable("chart-proj", "<p class=\"sub\">No data.</p>");
      return;
    }
    drawLine(m, k, s);
    facts_.innerHTML = facts(m, k, s);
    $("proj-axis").textContent = VARS[k].label.replace(" trend", "") + " in " + s + ", " + m.y0 + " to " + HORIZON + ". " + (m.fit ? "Dots: yearly values." : "Shown as change from the record’s average.") + " Solid line: fitted trend. Dashed line: projection.";
    var at = m.level(HORIZON);
    describe("chart-proj", "Line chart: " + VARS[k].label.replace(" trend", "") + " in " + s + ", measured to " + m.y1 + " and projected to " + HORIZON,
      "Trend " + sgn(m.slope / m.per, 3) + " " + m.unit + " " + perText(k) + ". Projected value in " + HORIZON + ": " + sgn(at.c) + " " + m.unit + ", 95% range of the trend line " + sgn(at.lo) + " to " + sgn(at.hi) + (m.fit ? ", and for a single year " + sgn(at.plo) + " to " + sgn(at.phi) : "") + ". Verdict on the trend: " + m.pub.verdict + ".");
    var years = []; for (var t = m.y0; t <= HORIZON; t += 5) years.push(t); if (years[years.length - 1] !== HORIZON) years.push(HORIZON);
    dataTable("chart-proj", table((m.fit ? "Fitted values" : "Change from the record’s average") + ", " + m.unit, m.fit ? ["Year", "Trend", "Trend 95% low", "Trend 95% high", "Single year low", "Single year high"] : ["Year", "Change", "95% low", "95% high"],
      years.map(function (y) { var l = m.level(y); return m.fit ? [String(y), sgn(l.c), sgn(l.lo), sgn(l.hi), sgn(l.plo), sgn(l.phi)] : [String(y), sgn(l.c, 1), sgn(l.lo, 1), sgn(l.hi, 1)]; })));
  }
  pv.addEventListener("change", drawAll); ps.addEventListener("change", drawAll);
  $("proj-csv").addEventListener("click", function () {
    var m = lastModel; if (!m) return;
    var rows = [m.fit ? "year,trend,trend_low95,trend_high95,single_year_low95,single_year_high95" : "year,change,low95,high95"];
    for (var t = m.y0; t <= HORIZON; t++) { var l = m.level(t); rows.push(m.fit ? [t, l.c, l.lo, l.hi, l.plo, l.phi].map(function (v, i) { return i ? v.toFixed(4) : v; }).join(",") : [t, l.c, l.lo, l.hi].map(function (v, i) { return i ? v.toFixed(4) : v; }).join(",")); }
    var a = document.createElement("a"), blob = new Blob(["# " + VARS[m.k].label + ", " + m.s + ", unit: " + m.unit + ". Straight-line projection to " + HORIZON + "; not a climate-model forecast.\n" + rows.join("\n") + "\n"], { type: "text/csv" });
    a.href = URL.createObjectURL(blob); a.download = "projection_" + m.k + "_" + m.s.toLowerCase() + ".csv"; document.body.appendChild(a); a.click(); a.remove();
  });
  drawAll();

  /* ---- content rendered later (link tables, Try tab): table captions and chart labels ---- */
  function nearestHeading(el) {
    var card = el.closest("article, section, .card"), h = card && card.querySelector("h2, h3");
    return h ? h.textContent.replace(/\s+/g, " ").trim() : "";
  }
  function fixA11y(root) {
    Array.prototype.forEach.call(root.querySelectorAll("table:not(.dtable)"), function (t) {
      if (!t.querySelector("caption")) {
        var cap = document.createElement("caption"); cap.className = "sr-only"; cap.textContent = nearestHeading(t) || "Data table";
        t.insertBefore(cap, t.firstChild);
      }
      Array.prototype.forEach.call(t.querySelectorAll("th:not([scope])"), function (th) { th.setAttribute("scope", t.rows[0] === th.parentNode ? "col" : "row"); });
    });
    Array.prototype.forEach.call(root.querySelectorAll("canvas:not([role])"), function (c) {
      c.setAttribute("role", "img");
      c.setAttribute("aria-label", (nearestHeading(c) || "Chart") + ". Chart; the same results are written out in the text and tables on this page.");
    });
  }
  fixA11y(document);
  if (window.MutationObserver && $("main")) {
    var pending = false;
    new MutationObserver(function () { if (pending) return; pending = true; setTimeout(function () { pending = false; fixA11y(document); }, 150); })
      .observe($("main"), { childList: true, subtree: true });
  }
})();
