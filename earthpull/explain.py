"""Plain-language explanations of computed results, written by an AI model through a local command-line tool.

The command is configured locally, not in this repo: set EXPLAIN_CMD (and optionally EXPLAIN_MODEL), or put the
command on the first line of data/explain_cmd.txt (and a model name on the second line). The command is called as
`<cmd> -p <prompt> [--model <model>] --tools "" --system-prompt <rules> --output-format text`. If it is not set or
fails, a deterministic template summary is shown instead.

Guarantees
1. The model only sees a fact sheet built here by code from the computed results: numbers, fixed verdict strings and
   physics-table reasons. Names come from the catalog, not from the browser.
2. A checker rejects any reply containing a number not in the fact sheet (rounding tolerated), banned words, em
   dashes or causal claims. One retry with the errors listed, then a deterministic template sentence.
3. Explanations are cached by the fact sheet's hash.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path

from .core import DATA, load_catalog

def _settings() -> tuple[str, str]:
    cmd, model = os.environ.get("EXPLAIN_CMD", ""), os.environ.get("EXPLAIN_MODEL", "")
    f = DATA / "explain_cmd.txt"  # local, git-ignored
    if not cmd and f.exists():
        lines = [x.strip() for x in f.read_text().splitlines()]
        cmd = lines[0] if lines else ""
        model = model or (lines[1] if len(lines) > 1 else "")
    return cmd, model


CMD, MODEL = _settings()
CACHE = DATA / "explanations"
VERDICTS = {"Clear rise", "Clear fall", "Likely change, but the two methods disagree",
            "No clear trend yet", "Too short to tell"}

STYLE = """You explain NASA climate-data results to high school and college students, inside a web tool.
Write like a sharp human science teacher. Rules:
- Use ONLY the numbers in the fact sheet. Never compute, convert, round differently or invent a number, year or source.
  If you need a number that is not there, describe it in words instead.
- Lead with what changed and how sure we are. Then one or two concrete details (which season, whether the start year
  matters, where in the region). Short sentences, active voice, plain words; explain any technical term in a few words.
- Say what the data shows, never why. Do not say "caused", "causes", "because of", "due to", "proves" or "proof".
  If a physics note is given, you may say "a known mechanism fits: <note>". Links between variables are
  "consistent with", never causes.
- "No clear trend yet" means the trend could be noise so far, not that there is no
  trend. Say so if it applies.
- Banned words: delve, foster, leverage, utilize, facilitate, empower, streamline, robust, cutting-edge, game changer,
  tapestry, realm, beacon, multifaceted, meticulous, intricate, paramount, transformative, elevate, embark, harness,
  crucial, crucially, importantly, notably, significantly (use "clearly" or give the p-value instead).
- No em dashes, no emoji, no headings, no bullet points, no "it's worth noting", no "this highlights/underscores",
  no "In conclusion"/"Overall" recap, no dramatic final line. End on the last concrete point.
- 3 to 5 sentences. Plain text only."""

BANNED = re.compile(r"\b(delve|foster|leverage|utili[sz]e|facilitate|empower|streamline|robust|cutting-edge|game changer|"
                    r"tapestry|realm|beacon|multifaceted|meticulous|intricate|paramount|transformative|elevate|embark|"
                    r"harness|crucial(ly)?|importantly|notably|significantly|caused|causes|because of|due to|proves?|proof|"
                    r"in conclusion|overall|it'?s worth noting|underscor\w*|highlight\w*)\b", re.I)


def _r(x, nd=3):
    """3 significant figures (2 for numbers under 0.1): readable numbers the model can quote exactly."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return None
    if x == 0:
        return 0.0
    sig = 2 if abs(x) < 0.1 else nd
    return float(f"{float(x):.{sig}g}")


def trend_facts(d: dict) -> dict:
    """Fact sheet for one variable's /api/analyze result."""
    cat = load_catalog()
    vid = d["variable"]["id"]
    src = cat[vid]
    t = d["trend"]
    v = t["verdict"] if t["verdict"] in VERDICTS else "Too short to tell"
    clear_seasons = [s for s in d.get("seasons", []) if s.get("verdict") in ("Clear rise", "Clear fall")]
    sens = d.get("sensitivity", [])
    sens_signs = {1 if s["rate"] > 0 else -1 for s in sens if s.get("rate") is not None}
    sens_sig = [s for s in sens if s.get("p") is not None and s["p"] < 0.05]
    facts = {
        "variable": src["name"], "measured by": src["instrument"], "units per decade": f"{d['variable']['units']}/decade",
        "region box (W,S,E,N)": [_r(d["region"][k], 2) for k in ("w", "s", "e", "n")],
        "record": f"{t['first']} to {t['last']}", "months with data": t["months"],
        "trend per decade": _r(t["slope_per_decade"]), "95% range low": _r(t["ci_low"]), "95% range high": _r(t["ci_high"]),
        "p-value (adjusted for month-to-month memory)": _r(t["p_ar1"], 4),
        "effective independent months": int(round(t["n_eff"])) if t.get("n_eff") else None,
        "verdict": v,
        "percent of average per decade": _r(t.get("pct_of_mean_per_decade")) if src.get("units") not in ("K", None, "") and vid != "water_storage" else None,
        "seasons or months with a clear trend": [f"{s['period']}: {_r(s['rate'])} per decade ({s['verdict']})" for s in clear_seasons][:6] or "none",
        "start-year check": ("same direction for every start year" if len(sens_signs) == 1 else
                             "direction depends on the start year" if sens_signs else "not enough years"),
        "start years tested": f"{sens[0]['start']} to {sens[-1]['start']}" if sens else None,
        "start years giving a significant trend": len(sens_sig),
    }
    m = d.get("map")
    if m:
        flat = [x for row in m["verdict"] for x in row]
        facts["grid cells in the map"] = {"rising clearly": flat.count(1), "falling clearly": flat.count(-1),
                                          "not significant": flat.count(0)}
    if src.get("caveat"):
        facts["dataset caveat"] = src["caveat"]
    return {k: v for k, v in facts.items() if v is not None}


def links_facts(d: dict, region: dict) -> dict:
    """Fact sheet for an /api/correlate result."""
    cat = load_catalog()
    nm = lambda v: cat.get(v, {}).get("name", v)
    links = []
    for p in d.get("pairs", []):
        if p.get("level", 0) >= 1:
            links.append({"pair": f"{nm(p['a'])} and {nm(p['b'])}", "r": _r(p["r"], 2),
                          "delay in months (positive = second follows first)": p["best_lag"],
                          "verdict": p["verdict"] if len(p["verdict"]) < 160 else p["verdict"][:160],
                          "physics note": p.get("why") or "none"})
    checks = [{"trend in": nm(c["y"]), "accounting for": nm(c["x"]),
               # a share is meaningless when the engine says the two cannot be separated (it can exceed 100%)
               "share explained (%)": None if (c["share_of_trend_x_accounts_for"] is None
                                               or str(c.get("verdict", "")).startswith("Cannot separate"))
               else int(round(100 * c["share_of_trend_x_accounts_for"])),
               "verdict": c["verdict"]} for c in d.get("trend_checks", [])
              if not str(c.get("verdict", "")).startswith("Trend still clear")][:6]
    return {"region box (W,S,E,N)": [_r(region[k], 2) for k in ("w", "s", "e", "n")],
            "variables tested": [nm(v["id"]) for v in d.get("variables", [])],
            "links found (seasons and trends removed)": links[:10] or "none",
            "pairs with no clear link": sum(1 for p in d.get("pairs", []) if p.get("level", 0) == 0),
            "trends partly explained or inseparable": checks or "none"}


STATE_VARS = {  # key in Tool data -> (label, unit, value field, low field, high field)
    "temp": ("air temperature", "degrees C per decade", "slope_per_decade", "ci_low", "ci_high"),
    "precip": ("precipitation", "% of the state's average per decade", "pct_per_decade", "pct_ci_low", "pct_ci_high"),
    "smoke": ("summer (June-August) smoke and haze, as aerosol optical depth", "per decade", "slope_per_decade", "ci_low", "ci_high"),
    "water": ("total water stored on and under the land (GRACE)", "mm of water per year", "slope_per_decade", "ci_low", "ci_high"),
    "soil": ("soil moisture in the top 10 cm", "% of the average per decade", "pct_per_decade", None, None),
}


def state_facts(name: str, st: dict) -> dict:
    """Fact sheet for one state from the Tool's per-state statistics (scripts/build_tool_data.py)."""
    facts = {"state": name, "regions": "US Census state outline"}
    for k, (label, unit, vf, lo, hi) in STATE_VARS.items():
        d = st.get(k, {})
        if d.get(vf) is None:
            facts[label] = d.get("verdict", "no data")
            continue
        item = {"trend": _r(d[vf]), "unit": unit, "verdict": d.get("verdict"), "record": d.get("record")}
        if lo and d.get(lo) is not None:
            item["95% range"] = [_r(d[lo]), _r(d[hi])]
        if k == "water" and d.get("km3_per_year") is not None:
            item["volume per year (km3), inside the state"] = _r(d["km3_per_year"])
            if d.get("km3_per_year_with_margin") is not None:
                item["volume per year (km3), with a 100 km margin"] = _r(d["km3_per_year_with_margin"])
        facts[label] = item
    return facts


def overview_facts(stats: dict) -> dict:
    """Fact sheet across all states: which variables have clear trends where."""
    out = {"states": list(stats)}
    for k, (label, unit, vf, _, _) in STATE_VARS.items():
        rows = {}
        for name, st in stats.items():
            d = st.get(k, {})
            rows[name] = (f"{_r(d[vf])} {unit} ({d.get('verdict')})" if d.get(vf) is not None else d.get("verdict", "no data"))
        out[label] = rows
    return out


def _numbers(text: str) -> list[float]:
    out = []
    for m in re.finditer(r"(?<![A-Za-z])[-+−]?\d+(?:[.,]\d+)*(?:\.\d+)?", text):
        s = m.group(0).replace("−", "-").replace(",", "")
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


def _allowed(facts) -> list[float]:
    vals = []

    def walk(x):
        if isinstance(x, dict):
            [walk(v) for v in x.values()]
        elif isinstance(x, list):
            [walk(v) for v in x]
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            vals.append(float(x))
        elif isinstance(x, str):
            vals.extend(_numbers(x))
    walk(facts)
    return vals


def check(text: str, facts: dict) -> list[str]:
    errs = []
    allowed = _allowed(facts) + [10, 95, 1, 2, 3, 4, 12]  # "per decade", "95% range", small counts/ordinals
    for n in _numbers(text):
        ok = any(abs(abs(n) - abs(a)) <= max(0.051 * max(abs(a), 1e-9), 0.0051 if abs(a) < 1 else 0.051) for a in allowed)
        if not ok:
            errs.append(f"number {n:g} is not in the fact sheet")
    if "—" in text:
        errs.append("contains an em dash")
    for w in sorted({m.group(0).lower() for m in BANNED.finditer(text)}):
        errs.append(f"uses a banned word or causal claim: '{w}'")
    if len(re.findall(r"[.!?](\s|$)", text)) > 8:
        errs.append("too many sentences")
    return errs


def template(kind: str, facts: dict) -> str:
    if kind == "state":
        clear = [f"{k} ({v['verdict'].lower()})" for k, v in facts.items() if isinstance(v, dict) and str(v.get("verdict", "")).startswith("Clear")]
        return (f"In {facts['state']}, the clear trends are: " + "; ".join(clear) + ". The other variables show no clear trend yet."
                if clear else f"In {facts['state']}, none of the variables shows a clear trend yet.")
    if kind == "overview":
        return "Air temperature, water storage and the other variables are compared across the five states in the charts below."
    if kind == "trend":
        return (f"{facts['variable']} in this region changed by {facts['trend per decade']} {facts['units per decade']} "
                f"over {facts['record']} (95% range {facts['95% range low']} to {facts['95% range high']}). "
                f"Verdict: {facts['verdict']}.")
    links = facts["links found (seasons and trends removed)"]
    if links == "none":
        return "None of the chosen variables move together here once seasons and trends are removed."
    return "Links found: " + "; ".join(f"{l['pair']} (r = {l['r']}, {l['verdict']})" for l in links[:4]) + "."


def _ask(system: str, prompt: str) -> str:
    if not CMD:
        raise RuntimeError("no explanation command configured (EXPLAIN_CMD or data/explain_cmd.txt)")
    work = DATA / "explain_tmp"
    work.mkdir(parents=True, exist_ok=True)  # neutral folder: no project instruction files are picked up
    args = [CMD, "-p", prompt] + (["--model", MODEL] if MODEL else []) + [
        "--tools", "", "--system-prompt", system, "--output-format", "text", "--no-session-persistence",
        "--strict-mcp-config"]
    r = subprocess.run(args, capture_output=True, text=True, timeout=120, cwd=work)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300] or "the explanation command exited with an error")
    return r.stdout.strip()


def explain(kind: str, facts: dict) -> dict:
    key = hashlib.sha1(json.dumps([kind, facts, MODEL or "haiku", STYLE], sort_keys=True).encode()).hexdigest()[:16]
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{key}.json"
    if f.exists():
        old = json.loads(f.read_text())
        if old.get("source") != "template":
            old["source"] = "ai"
        return old | {"cached": True}
    task = {"trend": "Explain this trend result for one region.",
            "links": "Explain which variables move together here and what the links and trend checks mean. "
                     "Mention the strongest links first.",
            "state": "Explain what is clearly changing in this state and what is not yet clear, strongest change "
                     "first. Use 4 to 6 sentences.",
            "overview": "Summarise what is changing across these five Pacific states: which changes are clear and "
                        "shared, which differ between states, and what is not yet clear. Use 4 to 6 sentences."}[kind]
    prompt = f"{task}\n\nFACT SHEET (JSON):\n{json.dumps(facts, indent=1, ensure_ascii=False)}"
    out = {"text": template(kind, facts), "source": "template", "errors": []}
    try:
        text = _ask(STYLE, prompt)
        errs = check(text, facts)
        if errs:
            text = _ask(STYLE, prompt + "\n\nYour previous answer broke these rules, fix them: " + "; ".join(errs)
                           + "\nPrevious answer:\n" + text)
            errs = check(text, facts)
        out = ({"text": text, "source": "ai", "errors": []} if not errs else
               out | {"errors": errs})
    except Exception as exc:  # CLI missing, not logged in, timeout: the template still explains
        out["errors"] = [f"AI explanation unavailable: {exc}"]
    f.write_text(json.dumps(out))
    return out | {"cached": False}
