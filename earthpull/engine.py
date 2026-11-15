"""Static correlation engine for one location. No AI: fixed statistics and a fixed physics table (links.yaml).

Layer 1  hygiene      seasonal cycle removed, then the trend (+ known instrument steps) removed with the same
                      fit as earthpull.trends; effective sample size from lag-1 autocorrelation (Bretherton et al.
                      1999); Benjamini-Hochberg across all pair-lags
Layer 2  together     lagged correlation for every pair; partial correlation controlling for all other variables
Layer 3  trend        is Y's trend still there once X is accounted for? Y fitted on time + seasonal harmonics
                      (+ steps) with and without X's anomalies, AR(1) effective-sample-size errors throughout (the
                      same noise model as earthpull.trends). Reports the share of Y's trend that X accounts for
                      and whether X's own effect is significant.
Layer 4  timing       Granger test both ways; surrogate test (phase-randomised series) for the best lag
Layer 5  physics      only pairs listed in links.yaml, with matching sign and delay, can reach the top verdict

Verdicts never say "causes". The strongest is "consistent with A influencing B".
"""
from __future__ import annotations

import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import stats

warnings.filterwarnings("ignore")
LINKS = Path(__file__).with_name("links.yaml")
MIN_MONTHS = 120
ALPHA = 0.05

LEVELS = {
    0: "No clear link",
    1: "Move together",
    2: "Move together, not explained by the other variables",
    3: "Timing points one way, but no known mechanism",
    4: "Consistent with {a} influencing {b}",
}


# ------------------------------------------------------------------ layer 1

def _grid(wide: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Regular monthly PeriodIndex (missing months become NaN rows) and decimal-year time."""
    idx = pd.PeriodIndex(wide.index, freq="M")
    w = wide.copy()
    w.index = idx
    w = w.groupby(level=0).mean()
    full = pd.period_range(w.index.min(), w.index.max(), freq="M")
    w = w.reindex(full)
    ty = np.array([p.year + (p.month - 0.5) / 12 for p in full], float)
    return w, ty


def prepare(wide: pd.DataFrame, breaks: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monthly anomalies (calendar-month means removed) and detrended anomalies. The trend (+ any known instrument
    steps) is removed with the same AR(1) fit as earthpull.trends, so two variables that only share a trend are
    not counted as linked."""
    from .trends import _ols_ar1

    wide, ty = _grid(wide)
    month = wide.index.month
    anom = wide - wide.groupby(month).transform("mean")
    det = anom.copy()
    for c in anom:
        y = anom[c].to_numpy(float)
        ok = np.isfinite(y)
        if ok.sum() > 24:
            det[c] = _ols_ar1(ty, y, ok, tuple((breaks or {}).get(c, ())))["resid"]
    return anom, det


def _lag1(x: np.ndarray) -> float:
    ok = np.isfinite(x[:-1]) & np.isfinite(x[1:])
    return float(np.corrcoef(x[:-1][ok], x[1:][ok])[0, 1]) if ok.sum() > 5 else 0.0


def _corr_p(x: np.ndarray, y: np.ndarray, r1x: float, r1y: float, extra_dof: int = 0):
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(ok.sum())
    if n < 24:
        return np.nan, np.nan, n, np.nan
    r = float(np.corrcoef(x[ok], y[ok])[0, 1])
    rr = max(min(r1x * r1y, 0.95), -0.95)
    n_eff = max(5.0, n * (1 - rr) / (1 + rr)) - extra_dof
    t = r * math.sqrt(max(n_eff - 2, 1) / max(1e-12, 1 - r * r))
    return r, float(2 * stats.t.sf(abs(t), max(n_eff - 2, 1))), n, n_eff


def _shift(s: pd.Series, lag: int) -> np.ndarray:
    """Positive lag: value of s `lag` months later."""
    return s.shift(-lag).values


# ------------------------------------------------------------------ layer 2

def pair_lags(det: pd.DataFrame, a: str, b: str, max_lag: int) -> pd.DataFrame:
    x = det[a].values
    r1a, r1b = _lag1(det[a].values), _lag1(det[b].values)
    rows = []
    for lag in range(-max_lag, max_lag + 1):  # positive: b after a
        r, p, n, ne = _corr_p(x, _shift(det[b], lag), r1a, r1b)
        rows.append({"a": a, "b": b, "lag": lag, "r": r, "p": p, "n": n, "n_eff": ne})
    return pd.DataFrame(rows)


def partial_corr(det: pd.DataFrame, a: str, b: str, lag: int, controls: list[str]) -> tuple[float, float]:
    """Correlation of a and b (at lag) after regressing out the control variables (same month as a)."""
    df = pd.DataFrame({"a": det[a].values, "b": _shift(det[b], lag)}, index=det.index)
    for c in controls:
        df[c] = det[c].values
    df = df.dropna()
    if len(df) < 36:
        return np.nan, np.nan
    if not controls:  # nothing else to control for: the partial correlation is the plain correlation
        r, p, _, _ = _corr_p(df["a"].values, df["b"].values, _lag1(df["a"].values), _lag1(df["b"].values))
        return r, p
    Z = np.c_[np.ones(len(df)), df[controls].values]
    ra = df["a"].values - Z @ np.linalg.lstsq(Z, df["a"].values, rcond=None)[0]
    rb = df["b"].values - Z @ np.linalg.lstsq(Z, df["b"].values, rcond=None)[0]
    r, p, _, _ = _corr_p(ra, rb, _lag1(ra), _lag1(rb), extra_dof=len(controls))
    return r, p


# ------------------------------------------------------------------ layer 3

def partial_trend(wide: pd.DataFrame, anom: pd.DataFrame, y: str, x: str, breaks: dict | None = None) -> dict:
    """Is y's trend still there once x is accounted for?

    y is fitted on time + seasonal harmonics (+ y's known steps), once alone and once with x's anomalies added,
    on the same months, with AR(1)-adjusted errors (same noise model as earthpull.trends)."""
    from .trends import _ols_ar1

    w, ty = _grid(wide[[y, x]])
    xa = anom[x].reindex(w.index).to_numpy(float)
    yy = w[y].to_numpy(float)
    ok = np.isfinite(yy) & np.isfinite(xa)
    if ok.sum() < MIN_MONTHS:
        return {}
    br = tuple((breaks or {}).get(y, ()))
    f0 = _ols_ar1(ty, yy, ok, br)
    f1 = _ols_ar1(ty, yy, ok, br, extra=xa)
    b0, b1 = 10 * f0["slope"], 10 * f1["slope"]
    x_trendiness = float(abs(np.corrcoef(ty[ok], xa[ok])[0, 1]))  # how much x is itself just a steady trend
    return {"y": y, "x": x, "x_trend_corr": x_trendiness, "months": int(ok.sum()),
            "trend_alone_per_decade": b0, "p_alone": f0["p"],
            "trend_with_x_per_decade": b1, "p_with_x": f1["p"],
            "x_effect": f1["extra"][0]["coef"], "x_effect_p": f1["extra"][0]["p"],
            "share_of_trend_x_accounts_for": (1 - b1 / b0) if b0 else np.nan}


# ------------------------------------------------------------------ layer 4

def _fill(s: pd.Series) -> pd.Series:
    return s.interpolate(limit=3, limit_direction="both")


def granger_p(det: pd.DataFrame, a: str, b: str, max_lag: int) -> float:
    """Smallest Granger p-value over lags 1..max_lag for 'a helps predict b'."""
    from statsmodels.tsa.stattools import grangercausalitytests

    df = pd.DataFrame({"b": _fill(det[b]), "a": _fill(det[a])}).dropna()
    if len(df) < 60 or max_lag < 1:
        return np.nan
    try:
        res = grangercausalitytests(df[["b", "a"]].values, maxlag=max_lag)  # statsmodels 0.15: no verbose arg
    except Exception:
        return np.nan
    return float(min(v[0]["ssr_ftest"][1] for v in res.values()))


def surrogate_p(det: pd.DataFrame, a: str, b: str, lag: int, r_obs: float, n: int = 500, seed: int = 0) -> float:
    """Share of phase-randomised versions of a (same spectrum, so same autocorrelation) that beat |r_obs|."""
    rng = np.random.default_rng(seed)
    xa = _fill(det[a]).values
    mask_a = np.isfinite(xa)
    if not mask_a.all():
        xa = np.where(mask_a, xa, np.nanmean(xa))
    y = _shift(det[b], lag)
    ok = np.isfinite(y) & np.isfinite(det[a].values)
    f = np.fft.rfft(xa - xa.mean())
    amp = np.abs(f)
    hits = 0
    for _ in range(n):
        ph = rng.uniform(0, 2 * np.pi, len(f))
        ph[0] = 0
        if len(xa) % 2 == 0:
            ph[-1] = 0
        s = np.fft.irfft(amp * np.exp(1j * ph), n=len(xa))
        r = np.corrcoef(s[ok], y[ok])[0, 1]
        hits += abs(r) >= abs(r_obs)
    return (hits + 1) / (n + 1)


# ------------------------------------------------------------------ layer 5

def physics() -> list[dict]:
    return yaml.safe_load(LINKS.read_text())


def find_rule(a: str, b: str) -> tuple[dict | None, bool]:
    """Rule for the pair and whether it is written a->b (True) or b->a (False)."""
    for r in physics():
        if (r["a"], r["b"]) == (a, b):
            return r, True
        if (r["a"], r["b"]) == (b, a):
            return r, False
    return None, True


# ------------------------------------------------------------------ run

def run(wide: pd.DataFrame, names: dict | None = None, max_lag: int = 3, n_surrogates: int = 500,
        breaks: dict | None = None) -> dict:
    from statsmodels.stats.multitest import multipletests

    names = names or {}
    nm = lambda v: names.get(v, v)
    keep = [c for c in wide.columns if wide[c].notna().sum() >= MIN_MONTHS]
    anom, det = prepare(wide[keep], breaks)

    # layer 2: all pair-lags, one FDR across everything
    lagtabs = [pair_lags(det, a, b, max_lag) for i, a in enumerate(keep) for b in keep[i + 1:]]
    lt = pd.concat(lagtabs, ignore_index=True) if lagtabs else pd.DataFrame()
    if len(lt):
        ok = lt.p.notna()
        lt.loc[ok, "q"] = multipletests(lt.loc[ok, "p"], method="fdr_bh")[1]

    pairs = []
    for (a, b), g in lt.groupby(["a", "b"], sort=False):
        g = g.dropna(subset=["r"])
        if g.empty:
            continue
        best = g.loc[g.r.abs().idxmax()]
        lag = int(best.lag)
        # orient so that 'lead' comes first (positive lag means b after a)
        lead, follow, lag_abs = (a, b, lag) if lag >= 0 else (b, a, -lag)
        controls = [c for c in keep if c not in (a, b)]
        pr, pp = partial_corr(det, a, b, lag, controls)
        g_ab, g_ba = granger_p(det, a, b, max_lag), granger_p(det, b, a, max_lag)
        sp = surrogate_p(det, a, b, lag, best.r, n_surrogates) if best.q < ALPHA else np.nan
        rule, forward = find_rule(a, b)

        level = 0
        if best.q < ALPHA and (np.isnan(sp) or sp < ALPHA):
            level = 1
            if np.isfinite(pp) and pp < ALPHA:
                level = 2
        note, verdict = "", LEVELS[level]
        if rule:
            cause, effect = (rule["a"], rule["b"])
            sign_ok = np.sign(best.r) == rule["sign"]
            # delay measured from the rule's cause to its effect
            d = lag if forward else -lag
            lag_ok = 0 <= d <= rule["max_lag"]
            if rule["kind"] == "same":
                verdict = ("Agree, as expected (two measures of the same thing)" if level >= 1 and sign_ok
                           else "Expected to agree but do not: check the data")
                note = rule["why"]
            elif rule["kind"] == "shared":
                verdict = ("Move together, consistent with a shared source (neither drives the other)"
                           if level >= 1 and sign_ok else LEVELS[level])
                note = rule["why"]
            else:
                if level >= 2 and sign_ok and lag_ok:
                    level = 4
                    verdict = LEVELS[4].format(a=nm(cause), b=nm(effect))
                elif level >= 1 and not sign_ok:
                    verdict = "Move together, but opposite to the expected direction: check"
                elif level >= 1:
                    verdict = LEVELS[level] + (" (delay outside the expected range)" if not lag_ok else
                                               " (does not survive controlling for the other variables)")
                note = rule["why"]
        elif level >= 2:
            one_way = [(x, y) for x, y, p_xy, p_yx in [(a, b, g_ab, g_ba), (b, a, g_ba, g_ab)]
                       if np.isfinite(p_xy) and p_xy < ALPHA and not (np.isfinite(p_yx) and p_yx < ALPHA)]
            if one_way:
                level = 3
                verdict = f"Timing points from {nm(one_way[0][0])} to {nm(one_way[0][1])}, but no known mechanism"
            note = "Not in the physics table: statistical association only."
        elif level == 1:
            note = "Not in the physics table: statistical association only."

        pairs.append({"a": a, "b": b, "best_lag": lag, "leader": lead if lag else "same month", "r": float(best.r),
                      "q": float(best.q), "n_eff": float(best.n_eff), "partial_r": pr, "partial_p": pp,
                      "granger_a_to_b_p": g_ab, "granger_b_to_a_p": g_ba, "surrogate_p": sp, "level": level,
                      "verdict": verdict, "rule": f"{rule['a']} -> {rule['b']} ({rule['kind']})" if rule else "",
                      "why": note})
    pairs = pd.DataFrame(pairs)
    if len(pairs):
        pairs = pairs.sort_values(["level", "r"], key=lambda s: s.abs() if s.name == "r" else s,
                                  ascending=False, ignore_index=True)

    # layer 3: for each variable, does its trend survive accounting for each other variable?
    pt = []
    for y in keep:
        for x in keep:
            if x != y:
                r = partial_trend(wide, anom, y, x, breaks)
                if r:
                    rule, fwd = find_rule(x, y)
                    r["physics_rule"] = bool(rule and rule["kind"] == "cause" and fwd)
                    pt.append(r)
    pt = pd.DataFrame(pt)
    if len(pt):
        def tv(r):
            if r.p_alone >= ALPHA:
                return "No clear trend to explain"
            if r.p_with_x < ALPHA:
                return "Trend still clear after accounting for X"
            # time is already in the fit, so a significant X effect comes from X's own month-to-month swings.
            # Refuse only when X adds nothing of its own, or is almost nothing but a trend.
            if r.x_effect_p >= ALPHA or r.x_trend_corr >= 0.9:
                # X adds no month-to-month explanatory power of its own: the trend got absorbed only because
                # both variables drift, so the data cannot say which drift explains which
                return "Cannot separate: both mostly drift together, so the data cannot tell them apart"
            if not r.physics_rule:
                if r.x_trend_corr >= 0.5:
                    # a short-term (weather) link multiplied by X's own long drift can absorb Y's trend without
                    # X explaining it; without a known mechanism the data cannot tell these apart
                    return "Cannot separate: both mostly drift together, so the data cannot tell them apart"
                return "Trend weakens once X is accounted for, but no known mechanism: association only"
            return "Trend no longer clear once X is accounted for: consistent with X explaining part of it"
        pt["verdict"] = pt.apply(tv, axis=1)

    return {"variables": keep, "anom": anom, "det": det, "lags": lt, "pairs": pairs, "partial_trends": pt}


# ------------------------------------------------------------------ compare one pair across places

def compare_regions(series: dict, a: str, b: str, max_lag: int = 3, breaks: dict | None = None,
                    names: dict | None = None) -> tuple[pd.DataFrame, str]:
    """series: {place: DataFrame with columns a and b (monthly)}. Same tests as run(), one pair, many places.

    Returns a table (one row per place) and a fixed-wording summary of whether the sign agrees across places."""
    from statsmodels.stats.multitest import multipletests

    names = names or {}
    rule, forward = find_rule(a, b)
    rows = []
    for place, w in series.items():
        if a not in w or b not in w or w[a].notna().sum() < MIN_MONTHS or w[b].notna().sum() < MIN_MONTHS:
            rows.append({"place": place, "verdict": "Not enough data"})
            continue
        _, det = prepare(w[[a, b]], breaks)
        lt = pair_lags(det, a, b, max_lag).dropna(subset=["p"])
        lt["q"] = multipletests(lt.p, method="fdr_bh")[1]
        best = lt.loc[lt.r.abs().idxmax()]
        sig = best.q < ALPHA
        row = {"place": place, "best_lag": int(best.lag), "r": float(best.r), "q": float(best.q),
               "n_eff": float(best.n_eff), "months": int(best.n)}
        if rule and rule["kind"] == "cause":
            d = int(best.lag) if forward else -int(best.lag)
            row["matches_physics"] = bool(sig and np.sign(best.r) == rule["sign"] and 0 <= d <= rule["max_lag"])
        row["verdict"] = ("Linked, same direction as the physics rule" if row.get("matches_physics")
                          else "Linked, opposite to the physics rule" if sig and rule and np.sign(best.r) != rule["sign"]
                          else "Linked" if sig else "No clear link")
        rows.append(row)
    tab = pd.DataFrame(rows)
    linked = tab[tab.get("q", pd.Series(dtype=float)) < ALPHA] if "q" in tab else tab.iloc[0:0]
    signs = set(np.sign(linked.r)) if len(linked) else set()
    nm = lambda v: names.get(v, v)
    if len(linked) == 0:
        summary = f"{nm(a)} and {nm(b)} show no clear link in any of these places."
    elif len(signs) == 1:
        word = "together (more of one, more of the other)" if signs == {1.0} else "in opposite directions"
        summary = (f"Where they are linked ({len(linked)} of {len(tab)} places), {nm(a)} and {nm(b)} move {word} "
                   f"everywhere. A consistent sign across places supports one shared mechanism.")
    else:
        pos = ", ".join(linked[linked.r > 0].place)
        neg = ", ".join(linked[linked.r < 0].place)
        summary = (f"The link flips by place: same direction in {pos}; opposite direction in {neg}. "
                   "The same process can push a variable different ways in different climates (for example "
                   "energy-limited vs water-limited evaporation). Check whether the places differ in that way.")
    if rule:
        summary += f" Physics rule: {rule['why']}"
    return tab, summary
