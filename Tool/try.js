/* "Try it out yourself": run the trend engine on any box in the world (needs the tool server, see About). */
(function () {
  const API = location.protocol.startsWith("http") ? "" : "http://localhost:8000";
  const $ = id => document.getElementById(id);
  const r2 = x => (x === null || x === undefined || isNaN(x)) ? "n/a" : (Math.abs(x) >= 100 ? x.toFixed(0) : Math.abs(x) >= 10 ? x.toFixed(1) : Math.abs(x) >= 1 ? x.toFixed(2) : Math.abs(x) >= 0.01 ? x.toFixed(3) : x.toExponential(2));
  const sign = x => (x > 0 ? "+" : "") + r2(x);
  const clear = v => v && (v.startsWith("Clear") || v.startsWith("Consistent with") || v.startsWith("Agree"));
  const badge = v => `<span class="verdict ${clear(v) ? "clear" : "unclear"}">${v}</span>`;
  const START_BOX = [-125, 32, -114, 49];  // Pacific coast until the user picks a headline or draws a box
  let map, drawn, gridLayer, VARS = [], charts = {}, ready = false, RESULTS = {};

  function setBox(b) {
    ["w", "s", "e", "n"].forEach((k, i) => $("try-" + k).value = b[i]);
    drawBox();
  }
  function getBox() { return ["w", "s", "e", "n"].map(k => parseFloat($("try-" + k).value)); }
  function drawBox() {
    const [w, s, e, n] = getBox();
    if ([w, s, e, n].some(isNaN)) return;
    if (drawn) map.removeLayer(drawn);
    drawn = L.rectangle([[s, w], [n, e]], { color: "#f1f3f5", weight: 2, fill: false, dashArray: "6 4" }).addTo(map);
    map.fitBounds(drawn.getBounds().pad(0.3));
  }

  window.initTry = function () {
    if (ready) { setTimeout(() => map.invalidateSize(), 50); return; }
    ready = true;
    map = L.map("try-map", { worldCopyJump: true }).setView([30, -40], 2);
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", { maxZoom: 10, attribution: "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors" }).addTo(map);
    loadNews();
    // draw a box: the button, or Shift + drag
    let start = null, temp = null, armed = false;
    $("try-draw").addEventListener("click", () => { armed = true; map.dragging.disable(); $("try-draw").textContent = "Drag on the map…"; });
    map.on("mousedown", ev => { if (!armed && !ev.originalEvent.shiftKey) return; start = ev.latlng; map.dragging.disable(); });
    map.on("mousemove", ev => {
      if (!start) return;
      if (temp) map.removeLayer(temp);
      temp = L.rectangle(L.latLngBounds(start, ev.latlng), { color: "#f1f3f5", weight: 1, fillOpacity: .08 }).addTo(map);
    });
    map.on("mouseup", ev => {
      if (!start) return;
      const b = L.latLngBounds(start, ev.latlng);
      if (temp) { map.removeLayer(temp); temp = null; }
      start = null; armed = false; map.dragging.enable(); $("try-draw").textContent = "Draw a box";
      document.querySelectorAll(".newsitem.active").forEach(x => x.classList.remove("active"));
      setBox([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map(v => +v.toFixed(2)));
    });
    ["w", "s", "e", "n"].forEach(k => $("try-" + k).addEventListener("change", drawBox));
    fetch(API + "/api/variables").then(r => r.json()).then(vs => {
      VARS = vs;
      $("try-vars").innerHTML = vs.map(v =>
        `<label class="check"><input type="checkbox" value="${v.id}" ${["air_temp", "precip", "water_storage"].includes(v.id) ? "checked" : ""}>
         ${v.name} <span class="sub">(${v.instrument}${v.fast ? "" : ", slow first time"})</span></label>`).join("");
      $("try-corr-vars").innerHTML = vs.filter(v => v.fast).map(v =>
        `<label class="check"><input type="checkbox" value="${v.id}" ${["air_temp", "precip", "soil_moisture", "evaporation", "water_storage"].includes(v.id) ? "checked" : ""}> ${v.name}</label>`).join("");
      $("try-status").textContent = "Ready. Pick a place and a variable.";
    }).catch(() => {
      $("try-status").innerHTML = `<strong>The tool server is not running.</strong> Start it with <code>.venv/bin/uvicorn earthpull.api:app --port 8000</code> and open <code>http://localhost:8000</code>.`;
    });
    setBox(START_BOX);
    $("try-run").addEventListener("click", runTrends);
    $("try-detail").addEventListener("change", e => RESULTS[e.target.value] && render(RESULTS[e.target.value]));
    $("try-corr-run").addEventListener("click", runCorr);
  };

  // headlines are outside text: always inserted with textContent, never as HTML, and never sent to the AI
  async function loadNews() {
    const box = $("try-news");
    try {
      const res = await fetch(API + "/api/news?days=7");
      if (!res.ok) throw new Error(res.statusText);
      const items = await res.json();
      box.innerHTML = "";
      if (!items.length) { box.innerHTML = `<p class="sub">No headlines with a recognisable place right now.</p>`; return; }
      items.forEach(it => {
        const b = document.createElement("button");
        b.className = "newsitem";
        const meta = document.createElement("span"); meta.className = "nmeta";
        const day = it.time ? new Date(it.time).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : it.date;  // reader's own time zone
        meta.textContent = `${day} · ${it.topic} · ${it.place}`;
        const title = document.createElement("span"); title.className = "ntitle";
        title.textContent = it.title + (it.source ? ` (${it.source})` : "");
        b.append(meta, title);
        b.addEventListener("click", () => {
          document.querySelectorAll(".newsitem.active").forEach(x => x.classList.remove("active"));
          b.classList.add("active");
          setBox(it.box);
          if (it.variables.length) document.querySelectorAll("#try-vars input").forEach(i => { i.checked = it.variables.includes(i.value); });
          $("try-status").textContent = `Box set to ${it.place} (${it.kind}). Variables picked for "${it.topic}". Press "Find the trends".`;
        });
        box.append(b);
      });
    } catch (err) {
      box.innerHTML = `<p class="sub">Headlines unavailable (needs the tool server and an internet connection).</p>`;
    }
  }

  function chart(id, cfg) { if (charts[id]) charts[id].destroy(); charts[id] = new Chart($(id), cfg); }
  function qs() {
    const [w, s, e, n] = getBox();
    return `w=${w}&s=${s}&e=${e}&n=${n}&start=${$("try-y0").value}&end=${$("try-y1").value}`;
  }

  // Progress for a trend run: one bar plus one chip per variable (waiting / loading / done / failed).
  let RUNNING = false;
  function showProgress(ids, state) {
    const done = ids.filter(v => state[v] === "done" || state[v] === "failed").length;
    const label = { waiting: "waiting", loading: "loading…", done: "done", failed: "failed" };
    const html = `<div class="pbar" role="progressbar" aria-valuemin="0" aria-valuemax="${ids.length}" aria-valuenow="${done}">` +
      `<span style="width:${Math.round(100 * done / ids.length)}%"></span></div>` +
      `<p class="sub">${done} of ${ids.length} variables ready${done < ids.length ? ". Results appear below as each one finishes." : "."}</p>` +
      `<ul class="pchips">${ids.map(v => `<li class="${state[v]}">${VARS.find(x => x.id === v).name}<em>${label[state[v]]}</em></li>`).join("")}</ul>`;
    for (const id of ["try-progress", "try-progress-top"]) { $(id).innerHTML = html; $(id).hidden = false; }
  }
  function corrGate() {
    const btn = $("try-corr-run");
    if (!btn) return;
    btn.disabled = RUNNING;
    if (RUNNING) $("try-corr-status").textContent = "Waiting for the trend run above to finish, so the engine uses the same data…";
    else if ($("try-corr-status").textContent.startsWith("Waiting")) $("try-corr-status").textContent = "";
  }

  async function runTrends() {
    const ids = [...document.querySelectorAll("#try-vars input:checked")].map(i => i.value);
    if (!ids.length) { $("try-status").textContent = "Pick at least one variable."; return; }
    // fast ones first, so the first results appear quickly
    ids.sort((a, b) => (VARS.find(x => x.id === b).fast ? 1 : 0) - (VARS.find(x => x.id === a).fast ? 1 : 0));
    RESULTS = {};
    $("try-summary").innerHTML = ""; $("try-detail").innerHTML = "";
    $("try-results").hidden = true;
    $("try-run").disabled = true;
    RUNNING = true; corrGate();
    const state = Object.fromEntries(ids.map(v => [v, "waiting"]));
    showProgress(ids, state);
    let shown = false;
    for (const [i, v] of ids.entries()) {
      const meta = VARS.find(x => x.id === v);
      state[v] = "loading"; showProgress(ids, state);
      $("try-status").textContent = `${i + 1} of ${ids.length}: fetching ${meta.name} and testing the trend… ${meta.fast ? "(seconds to a minute)" : "(first time can take several minutes)"}`;
      try {
        const res = await fetch(`${API}/api/analyze?${qs()}&var=${v}`);
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        const d = await res.json();
        RESULTS[v] = d;
        addSummary(d);
        $("try-detail").insertAdjacentHTML("beforeend", `<option value="${v}">${d.variable.name}</option>`);
        if (!shown) { render(d); shown = true; }
        state[v] = "done";
      } catch (err) {
        state[v] = "failed";
        $("try-summary").insertAdjacentHTML("beforeend",
          `<div class="kpi"><div class="k-label">${meta.name}</div><div class="k-val">n/a</div><div class="k-note">Could not analyse here: ${err.message}</div></div>`);
      }
      $("try-results").hidden = false;
      showProgress(ids, state);
    }
    $("try-status").textContent = `Done: ${Object.keys(RESULTS).length} of ${ids.length} variables.`;
    $("try-run").disabled = false;
    RUNNING = false; corrGate();
    setTimeout(() => { if (!RUNNING) $("try-progress-top").hidden = true; }, 4000);
  }

  function addSummary(d) {
    const t = d.trend, unit = `${d.variable.units}/decade`;
    $("try-summary").insertAdjacentHTML("beforeend",
      `<div class="kpi clickable" data-v="${d.variable.id}"><div class="k-label">${d.variable.name}</div>
       <div class="k-val">${sign(t.slope_per_decade)} <small>${unit}</small></div>
       <div class="k-note">${badge(t.verdict)} 95% range ${sign(t.ci_low)} to ${sign(t.ci_high)} · ${t.first} to ${t.last}</div></div>`);
    document.querySelector(`#try-summary [data-v="${d.variable.id}"]`).addEventListener("click", () => {
      $("try-detail").value = d.variable.id; render(d);
      $("try-title").scrollIntoView({ behavior: "smooth" });
    });
  }

  function render(d) {
    explain("trend", d, "try-explain", "try-explain-src");
    const t = d.trend, u = d.variable.units, unit = `${u}/decade`;
    $("try-results").hidden = false;
    $("try-title").textContent = `${d.variable.name} · ${d.variable.instrument} · ${t.first} to ${t.last}`;
    $("try-caveat").textContent = d.variable.caveat ? "Dataset note from our benchmark tests: " + d.variable.caveat : "";
    $("try-kpis").innerHTML = [
      ["Trend", `${sign(t.slope_per_decade)} <small>${unit}</small>`, badge(t.verdict)],
      ["95% range", `${sign(t.ci_low)} to ${sign(t.ci_high)}`, `Robust (Theil-Sen) check: ${sign(t.sen_per_decade)}`],
      ["Evidence", `p = ${r2(t.p_ar1)}`, `Memory between months r1 = ${r2(t.lag1_autocorr)}: ${t.months} months count as about ${Math.round(t.n_eff)}`],
    ].map(([l, v, note]) => `<div class="kpi"><div class="k-label">${l}</div><div class="k-val">${v}</div><div class="k-note">${note}</div></div>`).join("");
    const x = d.series.months;
    chart("try-chart-series", {
      type: "line",
      data: { labels: x, datasets: [
        { label: "95% range of the trend", data: d.series.hi, borderWidth: 0, pointRadius: 0, fill: false },
        { label: "95% range", data: d.series.lo, borderWidth: 0, pointRadius: 0, fill: "-1", backgroundColor: "rgba(232,89,12,0.22)" },
        { label: "monthly anomaly (seasons removed)", data: d.series.anomalies, borderColor: "#859099", borderWidth: 1, pointRadius: 0, spanGaps: false },
        { label: "trend", data: d.series.line, borderColor: "#e8590c", borderWidth: 3, pointRadius: 0 }
      ] },
      options: { plugins: { legend: { position: "bottom", labels: { filter: i => i.datasetIndex > 0 } } },
                 scales: { x: { ticks: { maxTicksLimit: 10 } }, y: { title: { display: true, text: u } } } }
    });
    const sd = d.seasons;
    chart("try-chart-seasons", {
      type: "bar",
      data: { labels: sd.map(s => s.period.split(" ")[0]), datasets: [
        { label: "trend", data: sd.map(s => s.rate), backgroundColor: sd.map(s => clear(s.verdict) ? (s.rate > 0 ? "#e8590c" : "#1c7ed6") : "#4a4f54"), order: 2 },
        { label: "95% range", data: sd.map(s => s.lo === null ? null : [s.lo, s.hi]), backgroundColor: "rgba(241,243,245,0.35)", barPercentage: 0.15, grouped: false, order: 1 }
      ] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => { const s = sd[c.dataIndex];
        return s.rate === null ? s.verdict : [`${sign(s.rate)} ${unit}`, `95%: ${sign(s.lo)} to ${sign(s.hi)}`, s.verdict, `${s.years} years`]; } } } },
                 scales: { y: { title: { display: true, text: unit } } } }
    });
    const sy = d.sensitivity;
    chart("try-chart-sens", {
      type: "line",
      data: { labels: sy.map(s => s.start), datasets: [
        { data: sy.map(s => s.hi), borderWidth: 0, pointRadius: 0, fill: false },
        { data: sy.map(s => s.lo), borderWidth: 0, pointRadius: 0, fill: "-1", backgroundColor: "rgba(28,126,214,0.22)" },
        { label: "trend to the end of the record", data: sy.map(s => s.rate), borderColor: "#f1f3f5", borderWidth: 2,
          pointBackgroundColor: sy.map(s => s.p < 0.05 ? "#e8590c" : "#4a4f54"), pointRadius: 4 }
      ] },
      options: { plugins: { legend: { display: false } }, scales: { x: { title: { display: true, text: "start year" } }, y: { title: { display: true, text: unit } } } }
    });
    // trend map on the main map
    if (gridLayer) { map.removeLayer(gridLayer); gridLayer = null; }
    $("try-map-legend").innerHTML = "";
    if (d.map) {
      const g = d.map, vals = g.slope.flat().filter((v, i) => v !== null && [1, -1].includes(g.verdict.flat()[i]));
      const m = Math.max(...vals.map(Math.abs), 1e-9);
      const col = v => { const t = Math.max(-1, Math.min(1, v / m));
        const mix = (a, b, f) => "#" + [0, 1, 2].map(i => Math.round(parseInt(a.substr(1 + 2 * i, 2), 16) * (1 - f) + parseInt(b.substr(1 + 2 * i, 2), 16) * f).toString(16).padStart(2, "0")).join("");
        return t < 0 ? mix("#f4f4f4", "#1c7ed6", -t) : mix("#f4f4f4", "#e8590c", t); };
      gridLayer = L.layerGroup();
      g.lat.forEach((la, i) => g.lon.forEach((lo, j) => {
        const v = g.slope[i][j], vd = g.verdict[i][j];
        if (v === null || vd === -9) return;
        L.rectangle([[la - g.dlat / 2, lo - g.dlon / 2], [la + g.dlat / 2, lo + g.dlon / 2]],
          { stroke: false, fillOpacity: vd === 0 ? 0.35 : 0.75, fillColor: vd === 0 ? "#4a4f54" : col(v) })
          .bindTooltip(`${sign(v)} ${unit}${vd === 0 ? " (not significant)" : ""}`).addTo(gridLayer);
      }));
      gridLayer.addTo(map);
      $("try-map-legend").innerHTML = `<div class="bar" style="background:linear-gradient(90deg,#1c7ed6,#f4f4f4,#e8590c)"></div>
        <div class="ends"><span>${sign(-m)}</span><span>0</span><span>${sign(m)} ${unit}</span></div>
        <p class="sub">Trend in every grid cell. Grey = not significant after the false-discovery correction (q &lt; ${g.alpha_fdr}).</p>`;
    } else {
      $("try-map-legend").innerHTML = `<p class="sub">No per-cell map for this variable (no global file on the server). The box average above is still exact.</p>`;
    }
  }

  // AI explanation: the server builds a fact sheet from these results, an AI model writes it,
  // and a checker rejects any number that is not in the results.
  async function explain(kind, result, outId, srcId) {
    $(outId).textContent = "The AI is reading the results and writing an explanation…";
    $(srcId).textContent = "";
    try {
      const [w, s, e, n] = getBox();
      const res = await fetch(`${API}/api/explain`, { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ kind, result, region: { w, s, e, n } }) });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      const d = await res.json();
      $(outId).textContent = d.text;
      $(srcId).textContent = d.source === "template"
        ? "Plain summary from the numbers (the AI explanation was unavailable or failed the number check)."
        : `Written by an AI model from the numbers above. Every number in it was checked against the results; the charts remain the source of truth.`;
    } catch (err) { $(outId).textContent = "Explanation unavailable: " + err.message; }
  }

  async function runCorr() {
    const ids = [...document.querySelectorAll("#try-corr-vars input:checked")].map(i => i.value);
    if (ids.length < 2) { $("try-corr-status").textContent = "Pick at least two variables."; return; }
    if (RUNNING) { corrGate(); return; }
    $("try-corr-status").textContent = `Fetching ${ids.length} variables and running the correlation engine… (about a minute)`;
    $("try-corr-run").disabled = true;
    $("try-corr-progress").hidden = false;
    try {
      const res = await fetch(`${API}/api/correlate?${qs()}&vars=${ids.join(",")}&lag=3`);
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      const cd = await res.json();
      renderCorr(cd);
      explain("links", cd, "try-corr-explain", "try-corr-explain-src");
      $("try-corr-status").textContent = "Done.";
    } catch (err) { $("try-corr-status").textContent = "Could not run: " + err.message; }
    $("try-corr-progress").hidden = true;
    $("try-corr-run").disabled = false;
  }

  function renderCorr(d) {
    const name = id => (d.variables.find(v => v.id === id) || { name: id }).name;
    const vs = d.variables.map(v => v.id);
    const R = {}; d.pairs.forEach(p => { if (p.level >= 1) { R[p.a + "|" + p.b] = p.r; R[p.b + "|" + p.a] = p.r; } });
    const cell = r => r === undefined ? `<td class="hm">·</td>` :
      `<td class="hm" style="background:${r > 0 ? `rgba(232,89,12,${Math.abs(r)})` : `rgba(28,126,214,${Math.abs(r)})`}">${r.toFixed(2)}</td>`;
    $("try-corr-matrix").innerHTML = `<table class="heat"><tr><th></th>${vs.map(v => `<th>${name(v)}</th>`).join("")}</tr>` +
      vs.map(a => `<tr><th>${name(a)}</th>${vs.map(b => a === b ? `<td class="hm">—</td>` : cell(R[a + "|" + b])).join("")}</tr>`).join("") + `</table>`;
    $("try-corr-pairs").innerHTML = `<table><tr><th>Verdict</th><th>Pair</th><th>Delay</th><th>r</th><th>r after controlling for the rest</th><th>Why (physics table)</th></tr>` +
      d.pairs.filter(p => p.level >= 1).map(p => `<tr><td>${badge(p.verdict)}</td><td>${name(p.a)} &amp; ${name(p.b)}</td><td>${p.best_lag} mo</td><td>${r2(p.r)}</td><td>${r2(p.partial_r)}</td><td class="sub">${p.why || ""}</td></tr>`).join("") +
      `</table>` + (d.pairs.some(p => p.level >= 1) ? "" : `<p class="sub">No clear links between these variables here.</p>`);
    $("try-corr-trends").innerHTML = d.trend_checks.length ? `<table><tr><th>Trend in</th><th>Accounting for</th><th>Share explained</th><th>Verdict</th></tr>` +
      d.trend_checks.map(c => `<tr><td>${name(c.y)}</td><td>${name(c.x)}</td><td>${c.share_of_trend_x_accounts_for === null ? "n/a" : Math.round(100 * c.share_of_trend_x_accounts_for) + "%"}</td><td class="sub">${c.verdict.replace(/\bX\b/g, name(c.x))}</td></tr>`).join("") + `</table>`
      : `<p class="sub">None of these variables has a clear trend here, so there is nothing to explain.</p>`;
    $("try-corr-out").hidden = false;
  }
})();
