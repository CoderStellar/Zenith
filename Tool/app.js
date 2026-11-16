(function () {
  /* ---------- Tabs ---------- */
  const tabs = ["home", "map", "try", "about"];  // same order as the tab bar (arrow keys follow it)
  let map, mapReady = false;
  function show(name) {
    tabs.forEach(t => {
      const sel = t === name;
      document.getElementById("tab-" + t).setAttribute("aria-selected", sel);
      document.getElementById("panel-" + t).hidden = !sel;
    });
    if (name === "map" && window.STATS) { initMap(); setTimeout(() => map.invalidateSize(), 50); }
    if (name === "try" && window.initTry) window.initTry();
    try { history.replaceState(null, "", "#" + name); } catch (e) {}
  }
  tabs.forEach((t, i) => {
    const b = document.getElementById("tab-" + t);
    b.addEventListener("click", () => show(t));
    b.addEventListener("keydown", e => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        show(n); document.getElementById("tab-" + n).focus();
      }
    });
  });

  const h0 = location.hash.replace("#", "");
  if (!window.STATS || !window.META) {  // data.js missing or still the old placeholder file
    document.getElementById("panel-home").insertAdjacentHTML("afterbegin",
      `<div class="banner" role="alert"><strong>No data loaded.</strong> <code>data.js</code> has not been generated yet.
       Run <code>python scripts/build_tool_data.py build</code> in the earthpull project, then reload.
       "Try it out yourself" still works.</div>`);
    show(tabs.includes(h0) ? h0 : "home");
    return;
  }
  const STATES = window.STATES, STATS = window.STATS, META = window.META;
  const names = Object.keys(STATES);
  const palette = { Alaska: "#3b7dd8", California: "#d9534f", Hawaii: "#1fa37a", Oregon: "#e69f00", Washington: "#8e5bd0" };

  /* ---------- Variables: how each real statistic is shown ---------- */
  // pick(s) returns {v, lo, hi, verdict} in display units for state s
  const VARS = {
    temp: {
      label: "Air temperature trend", unit: "°C/decade", colors: ["#2b6cb0", "#c0392b"],
      desc: "How fast near-surface air temperature has changed, 1980-2024 (MERRA-2 reanalysis, state average). Positive = warming.",
      pick: s => ({ v: STATS[s].temp.slope_per_decade, lo: STATS[s].temp.ci_low, hi: STATS[s].temp.ci_high, verdict: STATS[s].temp.verdict })
    },
    precip: {
      label: "Precipitation trend", unit: "%/decade", colors: ["#8a5a14", "#1f5fa8"],
      desc: "Change in average rain and snow, as % of the state's average per decade, 2001-2024 (GPM IMERG). Negative = drier.",
      pick: s => ({ v: STATS[s].precip.pct_per_decade, lo: STATS[s].precip.pct_ci_low, hi: STATS[s].precip.pct_ci_high, verdict: STATS[s].precip.verdict })
    },
    smoke: {
      label: "Summer smoke & haze trend", unit: "AOD/decade", colors: ["#2b6cb0", "#d35400"],
      desc: "Change in June-August aerosol optical depth (how hazy the air is; wildfire smoke raises it), summers 2003-2024 (MODIS Aqua).",
      pick: s => ({ v: STATS[s].smoke.slope_per_decade, lo: STATS[s].smoke.ci_low, hi: STATS[s].smoke.ci_high, verdict: STATS[s].smoke.verdict })
    },
    water: {
      label: "Total water storage trend", unit: "mm/yr", colors: ["#8a5a14", "#0b7a75"],
      desc: "Change in all water stored on and under the land (groundwater, soil, snow, lakes), 2003-2024 (GRACE/GRACE-FO). Negative = losing water.",
      pick: s => ({ v: STATS[s].water.slope_per_decade, lo: STATS[s].water.ci_low, hi: STATS[s].water.ci_high, verdict: STATS[s].water.verdict })
    },
    soil: {
      label: "Soil moisture trend", unit: "%/decade", colors: ["#8a5a14", "#1f8a4c"],
      desc: "Change in water in the top 10 cm of soil, as % of average per decade, 2003-2024 (GLDAS Noah model). Negative = drier soil.",
      pick: s => {
        const d = STATS[s].soil, k = d.pct_per_decade / d.slope_per_decade;
        return { v: d.pct_per_decade, lo: d.ci_low * k, hi: d.ci_high * k, verdict: d.verdict };
      }
    }
  };
  const keys = Object.keys(VARS);
  const r2 = x => (x === null || x === undefined || isNaN(x)) ? "n/a" : (Math.abs(x) >= 10 ? x.toFixed(1) : Math.abs(x) >= 1 ? x.toFixed(2) : x.toFixed(3));
  const sign = x => (x > 0 ? "+" : "") + r2(x);
  const fmt = (k, s) => { const p = VARS[k].pick(s); return `${sign(p.v)} ${VARS[k].unit}`; };
  const clear = verdict => verdict && (verdict.startsWith("Clear") || verdict.startsWith("Consistent with") || verdict.startsWith("Agree"));
  const MEANING = { "No clear trend yet": "The change so far is within normal year-to-year swings, so it could still be noise. A longer record may settle it." };
  const badge = verdict => `<span class="verdict ${clear(verdict) ? "clear" : "unclear"}" title="${MEANING[verdict] || ""}">${verdict}</span>`;

  /* ---------- Helpers ---------- */
  function mix(c1, c2, t) {
    const p = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
    const a = p(c1), b = p(c2);
    return "#" + a.map((v, i) => Math.round(v + (b[i] - v) * t).toString(16).padStart(2, "0")).join("");
  }
  function maxAbs(k) { return Math.max(...names.map(s => Math.abs(VARS[k].pick(s).v || 0))) || 1; }
  // diverging: falls toward colors[0], rises toward colors[1], zero = pale; unclear trends are washed out
  function colorFor(k, s) {
    const p = VARS[k].pick(s), t = Math.max(-1, Math.min(1, (p.v || 0) / maxAbs(k)));
    const c = t < 0 ? mix("#f4f4f4", VARS[k].colors[0], -t) : mix("#f4f4f4", VARS[k].colors[1], t);
    return clear(p.verdict) ? c : mix(c, "#d9d9d9", 0.55);
  }
  function fill(sel, items) { sel.innerHTML = items.map(([v, l]) => `<option value="${v}">${l}</option>`).join(""); }

  /* ---------- Banner and data date ---------- */
  { const dd = document.getElementById("data-date"); if (dd) dd.textContent = META.generated; }

  /* ---------- Home: AI summary (pre-written when data.js was built) ---------- */
  if (META.summary) {
    { // first two sentences: the headline findings; the rest is in the tables below
      const sents = META.summary.text.match(/[\s\S]*?[.!?](?=\s+[A-Z]|\s*$)/g) || [META.summary.text];  // a full stop before a capital, so "29.5" is not a break
      document.getElementById("home-explain").textContent = sents.slice(0, 2).join("").trim(); }
  }

  /* ---------- Home: KPIs ---------- */
  const kpiBox = document.getElementById("kpis");
  keys.forEach(k => {
    const v = VARS[k];
    const top = names.slice().sort((a, b) => Math.abs(v.pick(b).v) - Math.abs(v.pick(a).v))[0];
    const p = v.pick(top);
    kpiBox.insertAdjacentHTML("beforeend",
      `<div class="kpi"><div class="k-label">${v.label}</div><div class="k-val"><span class="num" data-target="${p.v}">${sign(p.v)}</span> <small>${v.unit}</small></div>
       <div class="k-note">Largest change: ${top}<br>${badge(p.verdict)}</div></div>`);
  });

  /* ---------- Home: count KPI figures up when they scroll into view ---------- */
  {
    const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    const nums = Array.prototype.slice.call(document.querySelectorAll("#kpis .num"));
    if (!reduce && "IntersectionObserver" in window) {
      const run = el => {
        const target = parseFloat(el.dataset.target), dur = 900, t0 = performance.now();
        const step = now => { const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3); el.textContent = sign(target * e); if (k < 1) requestAnimationFrame(step); else el.textContent = sign(target); };
        requestAnimationFrame(step);
      };
      const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { run(e.target); io.unobserve(e.target); } }), { threshold: 0.5 });
      nums.forEach(n => io.observe(n));
    }
  }

  const gridColor = getComputedStyle(document.documentElement).getPropertyValue("--border");
  Chart.defaults.color = getComputedStyle(document.body).color;
  Chart.defaults.borderColor = gridColor;
  Chart.defaults.maintainAspectRatio = false;

  /* ---------- Home: how much each state has warmed (stacked horizontal bar by period) ---------- */
  {
    const yrs = TREND.years, first = yrs[0], last = yrs[yrs.length - 1];
    const decades = [];
    for (let d = Math.floor(first / 10) * 10; d <= last; d += 10) decades.push(d);
    const decMean = (s, d) => {
      const vals = yrs.map((y, i) => (y >= d && y < d + 10 ? TREND.series[s][i] : null)).filter(v => v !== null && v !== undefined && !isNaN(v));
      return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    };
    const segLabels = [];
    for (let i = 1; i < decades.length; i++) segLabels.push(decades[i - 1] + "–" + (i === decades.length - 1 ? last : decades[i]));
    const warmRamp = ["#ffd27f", "#ffac4a", "#f1622e", "#b11226", "#6b0f1a"];
    const total = s => { let t = 0; for (let i = 1; i < decades.length; i++) { const a = decMean(s, decades[i]), b = decMean(s, decades[i - 1]); if (a != null && b != null) t += a - b; } return t; };
    const ordered = names.slice().sort((a, b) => total(a) - total(b));
    const datasets = segLabels.map((lab, si) => ({
      label: lab,
      data: ordered.map(s => { const a = decMean(s, decades[si + 1]), b = decMean(s, decades[si]); return (a != null && b != null) ? +(a - b).toFixed(3) : 0; }),
      backgroundColor: warmRamp[Math.min(si, warmRamp.length - 1)], borderWidth: 0
    }));
    const inkColor = getComputedStyle(document.body).color;
    const totalLabels = {
      id: "totalLabels",
      afterDatasetsDraw(chart) {
        const { ctx, scales: { x, y } } = chart;
        ctx.save(); ctx.font = "600 12px 'Inter Tight', sans-serif"; ctx.fillStyle = inkColor; ctx.textBaseline = "middle"; ctx.textAlign = "left";
        ordered.forEach(s => { const t = total(s); ctx.fillText(sign(t) + " °C", x.getPixelForValue(t) + 8, y.getPixelForValue(s)); });
        ctx.restore();
      }
    };
    new Chart(document.getElementById("chart-trend"), {
      type: "bar",
      data: { labels: ordered, datasets },
      options: { indexAxis: "y", layout: { padding: { right: 52 } },
        plugins: { legend: { position: "bottom" },
                   title: { display: true, text: "Warming by period, " + first + "–" + last, color: inkColor, font: { size: 13 }, padding: { bottom: 8 } },
                   tooltip: { callbacks: { title: items => ordered[items[0].dataIndex], label: c => "Warming " + c.dataset.label + ": " + sign(c.parsed.x) + " °C",
                                           footer: items => "Total " + first + "–" + last + ": " + sign(total(ordered[items[0].dataIndex])) + " °C" } } },
        scales: { x: { stacked: true, title: { display: true, text: "°C of warming (segments add up to the total)" } }, y: { stacked: true } } },
      plugins: [totalLabels]
    });
  }

  /* ---------- Home: state comparison with 95% ranges ---------- */
  const homeVar = document.getElementById("home-var");
  fill(homeVar, keys.map(k => [k, VARS[k].label]));
  const bar = new Chart(document.getElementById("chart-bar"), {
    type: "bar",
    data: { labels: names, datasets: [
      { label: "trend", data: [], backgroundColor: [], borderColor: [], borderWidth: 1.5, order: 2 },
      { label: "95% range", data: [], backgroundColor: "rgba(60,60,60,0.25)", borderColor: "rgba(60,60,60,0.6)", borderWidth: 1, barPercentage: 0.18, grouped: false, order: 1 }
    ] },
    options: { plugins: { legend: { display: false },
                          tooltip: { callbacks: { label: c => {
                            const s = names[c.dataIndex], p = VARS[homeVar.value].pick(s);
                            return [`${sign(p.v)} ${VARS[homeVar.value].unit}`, `95% range ${sign(p.lo)} to ${sign(p.hi)}`, p.verdict];
                          } } } } }
  });
  function updateBar() {
    const k = homeVar.value;
    bar.data.datasets[0].data = names.map(s => VARS[k].pick(s).v);
    bar.data.datasets[0].backgroundColor = names.map(s => clear(VARS[k].pick(s).verdict) ? palette[s] : palette[s] + "44");
    bar.data.datasets[0].borderColor = names.map(s => palette[s]);
    bar.data.datasets[1].data = names.map(s => [VARS[k].pick(s).lo, VARS[k].pick(s).hi]);
    bar.options.scales = { y: { title: { display: true, text: VARS[k].unit } } };
    bar.update();
    document.getElementById("bar-note").textContent = VARS[k].desc + " Solid bars: clear trend. Faded bars: no clear trend yet. Grey line: 95% range.";
  }
  homeVar.addEventListener("change", updateBar); updateBar();

  /* ---------- Home: change profile (radar, relative across the five states) ---------- */
  const homeState = document.getElementById("home-state");
  fill(homeState, names.map(s => [s, s]));
  function norm(k, s) {
    const vals = names.map(x => VARS[k].pick(x).v), lo = Math.min(...vals), hi = Math.max(...vals);
    return hi === lo ? 50 : Math.round(((VARS[k].pick(s).v - lo) / (hi - lo)) * 100);
  }
  const radar = new Chart(document.getElementById("chart-radar"), {
    type: "radar",
    data: { labels: keys.map(k => VARS[k].label.replace(" trend", "")), datasets: [{ label: "", data: [], fill: true }] },
    options: { plugins: { legend: { display: false },
                          tooltip: { callbacks: { label: c => `${fmt(keys[c.dataIndex], homeState.value)} (${VARS[keys[c.dataIndex]].pick(homeState.value).verdict})` } } },
               scales: { r: { min: 0, max: 100, ticks: { display: false } } } }
  });
  function updateRadar() {
    const s = homeState.value, d = radar.data.datasets[0];
    d.label = s; d.data = keys.map(k => norm(k, s));
    d.borderColor = palette[s]; d.backgroundColor = palette[s] + "44";
    radar.update();
    document.getElementById("radar-detail").innerHTML = keys.map(k =>
      `<li><span>${VARS[k].label}</span> <strong>${fmt(k, s)}</strong> ${badge(VARS[k].pick(s).verdict)}</li>`).join("");
  }
  homeState.addEventListener("change", updateRadar); updateRadar();

  /* ---------- Home: seasonal precipitation (real monthly averages) ---------- */
  new Chart(document.getElementById("chart-season"), {
    type: "line",
    data: { labels: SEASONAL.months, datasets: names.map(s => ({ label: s, data: SEASONAL.series[s], borderColor: palette[s], backgroundColor: palette[s], borderWidth: 2, pointRadius: 2, tension: .3 })) },
    options: { plugins: { legend: { position: "bottom" } }, scales: { y: { title: { display: true, text: "mm per month" } } } }
  });

  /* ---------- Home: temperature projection to 2050 (OLS, autocorrelation-adjusted 95% band) ---------- */
  const projState = document.getElementById("proj-state");
  if (projState && window.TREND) {
    fill(projState, names.map(s => [s, s]));
    function ols(xs, ys) {
      const n = xs.length, mx = xs.reduce((a, b) => a + b, 0) / n, my = ys.reduce((a, b) => a + b, 0) / n;
      let sxx = 0, sxy = 0;
      for (let i = 0; i < n; i++) { sxx += (xs[i] - mx) ** 2; sxy += (xs[i] - mx) * (ys[i] - my); }
      const b = sxy / sxx, a = my - b * mx, res = xs.map((x, i) => ys[i] - (a + b * x));
      const s2 = res.reduce((s, r) => s + r * r, 0) / (n - 2);
      let num = 0, den = 0;
      for (let i = 1; i < n; i++) num += res[i] * res[i - 1];
      for (let i = 0; i < n; i++) den += res[i] * res[i];
      let r1 = den ? num / den : 0; if (r1 < 0) r1 = 0;
      const neff = Math.max(4, Math.min(n, n * (1 - r1) / (1 + r1)));
      return { a, b, mx, sxx, s2, neff };
    }
    const proj = new Chart(document.getElementById("chart-proj"), {
      type: "line", data: { labels: [], datasets: [] },
      options: { plugins: { legend: { position: "bottom", labels: { filter: it => !it.text.startsWith("_") } } },
                 scales: { y: { title: { display: true, text: "°C vs " + TREND.baseline + " average" } }, x: { title: { display: true, text: "year" } } } }
    });
    function updateProj() {
      const s = projState.value, z = 1.96, endY = 2050, xs = [], ys = [];
      TREND.years.forEach((y, i) => { const v = TREND.series[s][i]; if (v != null && !isNaN(v)) { xs.push(y); ys.push(v); } });
      const m = ols(xs, ys), startY = xs[0], lastData = xs[xs.length - 1], labels = [], line = [], lo = [], hi = [];
      for (let y = startY; y <= endY; y++) {
        labels.push(y);
        const fit = m.a + m.b * y, se = Math.sqrt(m.s2 * (1 / m.neff + (y - m.mx) ** 2 / m.sxx));
        line.push(fit); lo.push(fit - z * se); hi.push(fit + z * se);
      }
      const obs = labels.map(y => { const i = TREND.years.indexOf(y); return i >= 0 ? TREND.series[s][i] : null; });
      proj.data.labels = labels;
      proj.data.datasets = [
        { label: "observed", data: obs, borderColor: "#aab2b8", backgroundColor: "#aab2b8", pointRadius: 2, showLine: false },
        { label: "trend", data: labels.map((y, i) => y <= lastData ? line[i] : null), borderColor: palette[s], borderWidth: 2.5, pointRadius: 0, spanGaps: false },
        { label: "projection to 2050", data: labels.map((y, i) => y >= lastData ? line[i] : null), borderColor: palette[s], borderWidth: 2.5, borderDash: [6, 4], pointRadius: 0, spanGaps: false },
        { label: "95% range", data: hi, borderColor: "transparent", backgroundColor: palette[s] + "22", pointRadius: 0, fill: "+1" },
        { label: "_lo", data: lo, borderColor: "transparent", pointRadius: 0, fill: false }
      ];
      proj.update();
      const at = m.a + m.b * 2050, seEnd = Math.sqrt(m.s2 * (1 / m.neff + (2050 - m.mx) ** 2 / m.sxx)), rate = m.b * 10;
      document.getElementById("proj-note").textContent =
        `If the ${startY}–${lastData} trend of ${sign(rate)} °C per decade holds, ${s}'s yearly temperature reaches about ${sign(at)} °C above the ${TREND.baseline} average by 2050 (95% range ${sign(at - z * seEnd)} to ${sign(at + z * seEnd)}). A straight-line extrapolation with the record's year-to-year scatter, not a climate-model forecast.`;
    }
    projState.addEventListener("change", updateProj); updateProj();
  }

  /* ---------- Home: What/Why/Who/How carousel (labelled tabs, arrows, swipe; all panels share one height) ---------- */
  {
    const car = document.getElementById("intro-carousel");
    if (car) {
      const panels = Array.prototype.slice.call(car.querySelectorAll(".car-panel"));
      const tabsWrap = car.querySelector(".car-tabs"), count = car.querySelector(".car-count");
      const prev = car.querySelector(".prev"), next = car.querySelector(".next");
      const pad = n => String(n).padStart(2, "0");
      const tabsEls = panels.map((p, i) => {
        const b = document.createElement("button");
        b.type = "button"; b.className = "car-tab"; b.setAttribute("role", "tab");
        b.id = "car-tab-" + i; p.id = "car-panel-" + i;
        b.setAttribute("aria-controls", p.id); p.setAttribute("aria-labelledby", b.id);
        b.textContent = p.querySelector("h3") ? p.querySelector("h3").textContent : "Panel " + (i + 1);
        b.addEventListener("click", () => go(i));
        b.addEventListener("keydown", e => {
          if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); go(cur + (e.key === "ArrowRight" ? 1 : -1)); tabsEls[cur].focus(); }
        });
        tabsWrap.appendChild(b);
        return b;
      });
      let cur = 0;
      function go(i) {
        cur = Math.max(0, Math.min(panels.length - 1, i));
        panels.forEach((p, k) => { p.classList.toggle("on", k === cur); p.setAttribute("aria-hidden", k !== cur); });
        tabsEls.forEach((b, k) => { b.setAttribute("aria-selected", k === cur); b.tabIndex = k === cur ? 0 : -1; });
        count.textContent = pad(cur + 1) + " / " + pad(panels.length);
        prev.disabled = cur === 0; next.disabled = cur === panels.length - 1;
      }
      prev.addEventListener("click", () => go(cur - 1));
      next.addEventListener("click", () => go(cur + 1));
      let x0 = null;  // swipe on touch screens
      const stage = car.querySelector(".car-stage");
      stage.addEventListener("touchstart", e => { x0 = e.touches[0].clientX; }, { passive: true });
      stage.addEventListener("touchend", e => {
        if (x0 === null) return;
        const dx = e.changedTouches[0].clientX - x0; x0 = null;
        if (Math.abs(dx) > 40) go(cur + (dx < 0 ? 1 : -1));
      });
      go(0);
    }
  }

  /* ---------- Home: subtle reveal-on-scroll animation (respects reduced motion) ---------- */
  if (!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) && "IntersectionObserver" in window) {
    const io = new IntersectionObserver(es => {
      let i = 0;
      es.forEach(e => { if (e.isIntersecting) { e.target.style.transitionDelay = (i * 60) + "ms"; i++; e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { threshold: 0.1 });
    document.querySelectorAll("#panel-home .card, #panel-home .kpi, #panel-home .intro, #panel-home .hero.slim").forEach(el => { el.classList.add("reveal"); io.observe(el); });
  }

  /* ---------- Home: what drives what (correlation engine, per state) ---------- */
  const VNAME = { air_temp: "Air temperature", precip: "Precipitation", soil_moisture: "Soil moisture", water_storage: "Water storage", aod_modis_aqua: "Smoke & haze" };
  const vn = id => VNAME[id] || id;
  const esc = s => String(s === null || s === undefined ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const linkState = document.getElementById("link-state");
  if (linkState && STATS[names[0]].links) {
    fill(linkState, names.map(s => [s, s]));
    const renderLinks = () => {
      const L_ = STATS[linkState.value].links, vs = L_.variables.map(v => v.id), R = {};
      L_.pairs.forEach(p => { if (p.level >= 1) { R[p.a + "|" + p.b] = p.r; R[p.b + "|" + p.a] = p.r; } });
      const cell = r => r === undefined ? `<td class="hm">·</td>` :
        `<td class="hm" style="background:${r > 0 ? `rgba(232,89,12,${Math.abs(r)})` : `rgba(28,126,214,${Math.abs(r)})`}">${r.toFixed(2)}</td>`;
      document.getElementById("link-matrix").innerHTML = `<table class="heat"><tr><th></th>${vs.map(v => `<th>${vn(v)}</th>`).join("")}</tr>` +
        vs.map(x => `<tr><th>${vn(x)}</th>${vs.map(y => x === y ? `<td class="hm">—</td>` : cell(R[x + "|" + y])).join("")}</tr>`).join("") + `</table>`;
      const found = L_.pairs.filter(p => p.level >= 1);
      document.getElementById("link-pairs").innerHTML = found.length ? `<table><tr><th>Verdict</th><th>Pair</th><th>Delay</th><th>r</th><th>Known mechanism</th></tr>` +
        found.map(p => `<tr><td>${badge(p.verdict.split(" (")[0])}</td><td>${vn(p.a)} &amp; ${vn(p.b)}</td><td>${p.best_lag} mo</td><td>${r2(p.r)}</td><td class="sub">${esc(p.why)}</td></tr>`).join("") + `</table>`
        : `<p class="sub">No clear links between these variables in ${linkState.value}.</p>`;
      const tc = L_.trend_checks;
      document.getElementById("link-trends").innerHTML = tc.length ? `<table><tr><th>Trend in</th><th>Accounting for</th><th>Verdict</th></tr>` +
        tc.map(c => `<tr><td>${vn(c.y)}</td><td>${vn(c.x)}</td><td class="sub">${esc(c.verdict.replace(/\bX\b/g, vn(c.x)))}</td></tr>`).join("") + `</table>`
        : `<p class="sub">No variable here has a clear trend to explain.</p>`;
      const ex = L_.explanation || {};
      document.getElementById("link-explain").textContent = ex.text || "";
      document.getElementById("link-explain-src").textContent = ex.source === "template" ? "Plain summary from the numbers."
        : "Written by an AI model from the engine's results; every number checked against them.";
    };
    linkState.addEventListener("change", renderLinks); renderLinks();
  }
  const cmpSel = document.getElementById("cmp-pair");
  if (cmpSel && META.compare) {
    fill(cmpSel, META.compare.map((c, i) => [i, `${vn(c.a)} & ${vn(c.b)}`]));
    const cmp = new Chart(document.getElementById("chart-cmp"), {
      type: "bar", data: { labels: [], datasets: [{ data: [], backgroundColor: [] }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => {
        const row = META.compare[cmpSel.value].rows[c.dataIndex]; return [`r = ${r2(row.r)}`, row.verdict, `delay ${row.best_lag} months`]; } } } },
        scales: { y: { min: -1, max: 1, title: { display: true, text: "correlation r (seasons and trends removed)" } } } }
    });
    const renderCmp = () => {
      const c = META.compare[cmpSel.value], rows = c.rows.filter(r => r.r !== null && r.r !== undefined);
      cmp.data.labels = rows.map(r => r.place);
      cmp.data.datasets[0].data = rows.map(r => r.r);
      cmp.data.datasets[0].backgroundColor = rows.map(r => r.verdict.startsWith("Linked") ? palette[r.place] : palette[r.place] + "44");
      cmp.update();
      document.getElementById("cmp-summary").textContent = c.summary + " Solid bars: clear link; faded bars: no clear link.";
    };
    cmpSel.addEventListener("change", renderCmp); renderCmp();
  }

  /* ---------- Map ---------- */
  const mapVar = document.getElementById("map-var");
  fill(mapVar, keys.map(k => [k, VARS[k].label]));
  let geoLayer = null, markers = {}, selected = null, gridLayer = null;
  const mapGrid = document.getElementById("map-grid");
  function drawGrid() {
    if (!gridLayer) return;
    gridLayer.clearLayers();
    const k = mapGrid.value, gl = document.getElementById("grid-legend");
    if (!k || !window.GRIDS || !GRIDS[k]) { gl.innerHTML = ""; return; }
    const g = GRIDS[k], sig = g.cells.filter(c => c[3] !== 0).map(c => Math.abs(c[2]));
    const m = sig.length ? sig.sort((a, b) => a - b)[Math.floor(sig.length * 0.98)] : 1;
    g.cells.forEach(([la, lo, v, vd]) => {
      const t = Math.max(-1, Math.min(1, v / m));
      const fillColor = vd === 0 ? "#4a4f54" : (t < 0 ? mix("#f4f4f4", "#1c7ed6", -t) : mix("#f4f4f4", "#e8590c", t));
      L.rectangle([[la - g.dlat / 2, lo - g.dlon / 2], [la + g.dlat / 2, lo + g.dlon / 2]],
        { stroke: false, fillOpacity: vd === 0 ? 0.35 : 0.7, fillColor })
        .bindTooltip(`${sign(v)} ${g.unit}${vd === 0 ? " (not significant)" : ""}`).addTo(gridLayer);
    });
    if (geoLayer) geoLayer.setStyle(f => ({ color: "#f1f3f5", weight: 1, fillOpacity: 0 }));
    gl.innerHTML = `<div class="bar" style="background:linear-gradient(90deg,#1c7ed6,#f4f4f4,#e8590c)"></div>
      <div class="ends"><span>${sign(-m)}</span><span>0</span><span>${sign(m)} ${g.unit}</span></div>
      <p class="sub">${g.label}, ${g.note}. Every grid cell tested; grey = not significant after the false-discovery correction (q &lt; ${g.alpha_fdr}). State colours are hidden while this is on.</p>`;
  }
  mapGrid.addEventListener("change", () => { drawGrid(); if (!mapGrid.value) updateMap(); });

  function initMap() {
    if (mapReady) return; mapReady = true;
    map = L.map("map", { worldCopyJump: true }).setView([46, -135], 3);
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", { maxZoom: 10, attribution: "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors" }).addTo(map);
    names.forEach(s => {
      markers[s] = L.circleMarker(STATES[s].center, { radius: 12, weight: 2, color: "#222", fillOpacity: .9 }).addTo(map)
        .bindTooltip(s).on("click", () => selectState(s));
    });
    map.fitBounds(L.latLngBounds(names.map(s => STATES[s].center)).pad(.4));
    // bounding boxes: the West Coast analysis boxes (solid) and each state's bounding box (dashed)
    const boxLayer = L.layerGroup(), stateBoxLayer = L.layerGroup();
    if (window.BOXES) Object.entries(BOXES).forEach(([nm, [w, s, e, n]]) =>
      L.rectangle([[s, w], [n, e]], { color: "#f1f3f5", weight: 2, fill: false }).bindTooltip(nm + " analysis box").addTo(boxLayer));
    if (window.STATE_BOXES) Object.entries(STATE_BOXES).forEach(([nm, [w, s, e, n]]) =>
      L.rectangle([[s, w], [n, e]], { color: palette[nm] || "#859099", weight: 1.5, dashArray: "5 5", fill: false })
        .bindTooltip(nm + " bounding box").addTo(stateBoxLayer));
    boxLayer.addTo(map); stateBoxLayer.addTo(map);
    gridLayer = L.layerGroup().addTo(map);
    L.control.layers(null, { "Analysis boxes": boxLayer, "State bounding boxes": stateBoxLayer, "Trend map": gridLayer },
                     { collapsed: false }).addTo(map);
    fetch("https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json")
      .then(r => r.json())
      .then(g => {
        g.features = g.features.filter(f => names.includes(f.properties.name));
        geoLayer = L.geoJSON(g, {
          style: f => ({ color: "#333", weight: 1, fillColor: colorFor(mapVar.value, f.properties.name), fillOpacity: .8 }),
          onEachFeature: (f, l) => l.on("click", () => selectState(f.properties.name))
        }).addTo(map);
        geoLayer.bringToBack();
      })
      .catch(() => {});
    updateMap();
  }

  function updateMap() {
    const k = mapVar.value, v = VARS[k], m = maxAbs(k);
    document.getElementById("var-desc").textContent = v.desc;
    names.forEach(s => markers[s] && markers[s].setStyle({ fillColor: colorFor(k, s) }));
    if (geoLayer && !mapGrid.value) geoLayer.setStyle(f => ({ color: "#333", weight: 1, fillColor: colorFor(k, f.properties.name), fillOpacity: .8 }));
    document.getElementById("legend").innerHTML =
      `<div class="bar" style="background:linear-gradient(90deg,${v.colors[0]},#f4f4f4,${v.colors[1]})"></div>
       <div class="ends"><span>${sign(-m)} ${v.unit}</span><span>0</span><span>${sign(m)} ${v.unit}</span></div>
       <p class="sub">Washed-out colour = no clear trend yet.</p>`;
    const ranked = names.slice().sort((a, b) => v.pick(b).v - v.pick(a).v);
    document.getElementById("ranking").innerHTML = ranked.map(s =>
      `<li><button data-s="${s}" class="${s === selected ? "active" : ""}"><span>${s}</span><strong>${fmt(k, s)}</strong></button></li>`).join("");
    document.querySelectorAll("#ranking button").forEach(b => b.addEventListener("click", () => selectState(b.dataset.s)));
  }

  function selectState(s) {
    selected = s;
    map.setView(STATES[s].center, STATES[s].zoom);
    const w = STATS[s].water;
    const ex = STATS[s].explanation;
    document.getElementById("state-detail").innerHTML =
      `<h3>${s}</h3>` + (ex ? `<p class="lede small">${ex.text}</p><p class="sub">${ex.source === "template" ? "Plain summary from the numbers." : "Written by an AI model from these numbers; every number checked."}</p>` : "") +
      `<table><tr><th>Variable</th><th>Trend</th><th>95% range</th><th>Verdict</th></tr>` +
      keys.map(k => { const p = VARS[k].pick(s);
        return `<tr><td>${VARS[k].label}</td><td>${sign(p.v)} ${VARS[k].unit}</td><td>${sign(p.lo)} to ${sign(p.hi)}</td><td>${badge(p.verdict)}</td></tr>`; }).join("") +
      `</table>
       <p class="sub">Water volume: ${sign(w.km3_per_year)} km³/yr inside the state` +
      (w.km3_per_year_with_margin !== null ? ` (${sign(w.km3_per_year_with_margin)} km³/yr with a 100 km margin; GRACE's coarse footprint smears signal across borders)` : "") +
      (w.reliable ? "" : `. <strong>Caution:</strong> ${s} is small compared with GRACE's ~300 km footprint, so its water trend is unreliable.`) +
      `. Average temperature ${STATS[s].temp.mean} °C; average precipitation ${STATS[s].precip.mean_mm_per_year} mm/yr.</p>` +
      (STATS[s].links ? `<h3>Strongest links</h3><ul class="profile">` + STATS[s].links.pairs.filter(p => p.level >= 1)
        .sort((x, y) => y.level - x.level || Math.abs(y.r) - Math.abs(x.r)).slice(0, 4)
        .map(p => `<li><span>${vn(p.a)} &amp; ${vn(p.b)}</span> <strong>r = ${r2(p.r)}</strong> ${badge(p.verdict.split(" (")[0])}</li>`).join("") +
        `</ul><p class="sub">Full details on the Homepage under "What drives what?".</p>` : "");
    updateMap();
  }
  mapVar.addEventListener("change", updateMap);

  /* ---------- About: dataset caveats from the benchmark tests ---------- */
  const cav = document.getElementById("caveats");
  if (cav) cav.innerHTML = Object.values(META.datasets).filter(d => d.caveat).map(d =>
    `<li><strong>${d.name}</strong> (${d.product}): ${d.caveat}</li>`).join("");

  /* ---------- Landing: "Six things Zenith does differently" (compact; every number comes from the data) ---------- */
  (function () {
    const list = document.getElementById("diff-list");
    if (!list) return;
    const f2 = x => (x >= 0 ? "+" : "\u2212") + Math.abs(x).toFixed(2);
    const cells = [];
    const noClear = names.filter(s => /no clear/i.test(STATS[s].precip.verdict || "")).length;
    const warm = names.filter(s => /clear rise/i.test(STATS[s].temp.verdict || "")).length;
    cells.push(`<h3>Says when it doesn\u2019t know</h3><p class="r-big">Rain: no clear trend, ${noClear} of ${names.length}</p>
      <p class="r-note">Temperature: clear rise, ${warm} of ${names.length}.</p>`);
    const ca = (STATS.California && STATS.California.links && STATS.California.links.pairs) || [];
    const rw = ca.find(p => p.a === "precip" && p.b === "water_storage");
    if (rw) cells.push(`<h3>Won\u2019t claim a weak link</h3><p class="r-big">r ${rw.r.toFixed(2)} \u2192 ${rw.partial_r.toFixed(2)}</p>
      <p class="r-note">California rain vs. water storage, once soil moisture is controlled.</p>`);
    const cmp = (META.compare || []).find(c => c.a === "air_temp" && c.b === "soil_moisture");
    if (cmp) {
      const mx = Math.max(...cmp.rows.map(r => Math.abs(r.r)), 0.01);
      const bars = cmp.rows.map(r => { const w = Math.round(100 * Math.abs(r.r) / mx);
        return `<div class="flip"><span>${r.place}</span><div class="neg">${r.r < 0 ? `<span style="width:${w}%"></span>` : ""}</div>` +
               `<div class="pos">${r.r > 0 ? `<span style="width:${w}%"></span>` : ""}</div><span class="val">${f2(r.r)}</span></div>`; }).join("");
      const flipped = cmp.rows.filter(r => r.r > 0).map(r => r.place);
      cells.push(`<h3>Flags when places disagree</h3><div>${bars}</div>
        <p class="r-note">Warmer means drier soil${flipped.length ? `, except ${flipped.join(" and ")}` : ""}.</p>`);
    }
    cells.push(`<h3>Checked against published science</h3><p class="r-big">13 of 16 match</p>
      <p class="r-note">The 3 misses are shown, with reasons.</p>
      <button class="r-link" type="button" data-go="about">See the benchmarks</button>`);
    cells.push(`<h3>Summaries can\u2019t invent numbers</h3><p class="r-big">Every number checked</p>
      <p class="r-note">Against the computed results, before you see it.</p>`);
    cells.push(`<h3>From the news to NASA data</h3><p class="r-big">Any box on Earth</p>
      <p class="r-note">Click a headline; the same tests run.</p>
      <button class="r-link" type="button" data-go="try">Try it out yourself</button>`);
    list.innerHTML = cells.map(c => `<li>${c}</li>`).join("");
    list.querySelectorAll("[data-go]").forEach(b => b.addEventListener("click", () => {
      show(b.dataset.go);
      if (b.dataset.go === "about") setTimeout(() => { const t = document.getElementById("benchmarks"); if (t) t.scrollIntoView(); }, 50);
      else window.scrollTo(0, 0);
    }));
  })();

  /* ---------- Initial tab from URL hash ---------- */
  show(tabs.includes(h0) ? h0 : "home");
})();
