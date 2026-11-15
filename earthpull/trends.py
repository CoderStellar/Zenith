"""Trend tests for monthly regional series, following reports/Trend analysis methods for Earth data.md.

One noise model drives every number on screen, so the rate, its range, the p-value and the verdict cannot
contradict each other:

1. PRIMARY  OLS trend fitted jointly with annual + semiannual harmonics (+ step terms at documented product
            changes) on real decimal time. Significance and 95% range use the AR(1) effective sample size
            n_eff = n (1 - r1) / (1 + r1) (Santer et al. 2008), as IPCC AR6 does. Gaps stay gaps: nothing is
            interpolated across them.
2. CHECK    Theil-Sen slope on monthly anomalies with Sen's rank-based CI, whose Mann-Kendall variance is
            inflated by n / n_eff (same memory correction). A trend is "clear" only when this agrees.
3. DISPLAY  Hamed-Rao Mann-Kendall with lag=3 on (near) gap-free series. Shown, never decides.
4. FAMILY   Benjamini-Hochberg across the variables tested together, on the primary p-value.
5. DETECT   Weatherhead et al. (1998) years needed for the current slope, from the fit's residuals.
            The 3.3 constant has not been re-checked against the paper.

The plain OLS t-test (p_ttest) is kept only as a teaching foil: it ignores memory.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

MIN_MONTHS = 120
ALPHA = 0.05


def _to_monthly(s: pd.Series) -> pd.Series:
    """Regular monthly grid (month start); missing months become NaN."""
    s = s.copy()
    if isinstance(s.index, pd.PeriodIndex):
        s.index = s.index.to_timestamp()
    s.index = pd.to_datetime(s.index).to_period("M").to_timestamp()
    s = s.groupby(level=0).mean()
    return s.asfreq("MS")


def _lag1(e: np.ndarray) -> float:
    """Lag-1 autocorrelation on a regular grid that may contain NaN (pairs across a gap are skipped)."""
    m = np.nanmean(e)
    a, b = e[:-1], e[1:]
    ok = np.isfinite(a) & np.isfinite(b)
    den = np.nansum((e - m) ** 2)
    return float(np.sum((a[ok] - m) * (b[ok] - m)) / den) if den > 0 else 0.0


def _design(ty: np.ndarray, breaks=()) -> np.ndarray:
    w = 2 * np.pi * ty
    cols = [np.ones_like(ty), ty - ty.mean(), np.sin(w), np.cos(w), np.sin(2 * w), np.cos(2 * w)]
    cols += [(ty >= b).astype(float) for b in breaks]
    return np.column_stack(cols)


def _ols_ar1(ty: np.ndarray, y: np.ndarray, ok: np.ndarray, breaks=(), alpha: float = ALPHA,
             extra: np.ndarray | None = None) -> dict:
    """Trend + harmonics (+ steps) (+ extra regressors) by least squares; AR(1)-adjusted standard error of the
    trend and of each extra regressor. `extra` is (len(y), k) on the same grid as y; rows with NaN are skipped."""
    scale = None
    if extra is not None:
        extra = np.asarray(extra, float).reshape(len(y), -1)
        ok = ok & np.isfinite(extra).all(axis=1)
        # rescale so a variable like NO2 (~1e15) does not swamp the solver; coefficients are scaled back below
        scale = np.nanstd(extra[ok], axis=0)
        scale[~(scale > 0)] = 1.0
    X = _design(ty[ok], breaks)
    if extra is not None:
        X = np.column_stack([X, extra[ok] / scale])
    p = X.shape[1]
    n = int(ok.sum())
    beta, *_ = np.linalg.lstsq(X, y[ok], rcond=None)
    e = np.full_like(y, np.nan)
    e[ok] = y[ok] - X @ beta
    r1 = min(max(_lag1(e), 0.0), 0.99)
    ne = n * (1 - r1) / (1 + r1)
    dof = max(ne - p, 1.0)
    sse = np.nansum(e ** 2)
    XtX_inv = np.linalg.pinv(X.T @ X)  # exact SE even when steps or extra regressors correlate with time
    se = float(np.sqrt(sse / dof * XtX_inv[1, 1]))
    slope = float(beta[1])  # units per year
    tcrit = stats.t.ppf(1 - alpha / 2, dof)
    se_naive = float(np.sqrt(sse / max(n - p, 1) * XtX_inv[1, 1]))
    out_extra = {}
    if extra is not None:  # AR(1)-adjusted significance of each extra regressor, same noise model
        k = extra.shape[1]
        for c in range(k):
            col = X.shape[1] - k + c
            se_c = np.sqrt(sse / dof * XtX_inv[col, col])
            out_extra[c] = {"coef": float(beta[col] / scale[c]),
                            "p": float(2 * stats.t.sf(abs(beta[col] / se_c), dof)) if se_c > 0 else np.nan}
    return {"slope": slope, "se": se, "lo": slope - tcrit * se, "hi": slope + tcrit * se, "resid": e,
            "extra": out_extra, "n": n,
            "p": float(2 * stats.t.sf(abs(slope / se), dof)) if se > 0 else np.nan,
            "p_naive": float(2 * stats.t.sf(abs(slope / se_naive), max(n - p, 1))) if se_naive > 0 else np.nan,
            "r1": r1, "n_eff": ne, "sigma": float(np.nanstd(e, ddof=p))}


def trend_report(s: pd.Series, breaks=(), alpha: float = ALPHA) -> dict:
    """s: monthly series (DatetimeIndex or PeriodIndex; gaps as NaN or missing rows).
    breaks: decimal years of documented product changes, e.g. (2018.42,) for the GRACE-FO start."""
    import pymannkendall as mk

    s = _to_monthly(s)
    ty = (s.index.year + (s.index.month - 0.5) / 12).to_numpy(float)
    y = s.to_numpy(float)
    ok = np.isfinite(y)
    n = int(ok.sum())
    out = {"months": n, "first": str(s.first_valid_index())[:7] if n else None,
           "last": str(s.last_valid_index())[:7] if n else None}
    if n < MIN_MONTHS:
        out["too_short"] = True
        return out

    # 1) primary: OLS + harmonics (+ steps), AR(1)-adjusted
    f = _ols_ar1(ty, y, ok, breaks, alpha)
    out.update(slope_per_decade=10 * f["slope"], ci_low=10 * f["lo"], ci_high=10 * f["hi"], p_ar1=f["p"],
               p_ttest=f["p_naive"], lag1_autocorr=f["r1"], n_eff=f["n_eff"], short_memory_flag=f["n_eff"] < 30,
               record_years=float(ty[ok][-1] - ty[ok][0]))
    if breaks:  # same fit without the steps: is the answer robust to known instrument changes?
        f0 = _ols_ar1(ty, y, ok, (), alpha)
        out.update(slope_no_steps_per_decade=10 * f0["slope"], p_no_steps=f0["p"],
                   robust_to_breaks=bool(np.sign(f0["slope"]) == np.sign(f["slope"])
                                         and (f0["p"] < alpha) == (f["p"] < alpha)))

    # 2) robust check: Sen slope on anomalies, rank CI with MK variance x n/n_eff
    anom = (s - s.groupby(s.index.month).transform("mean")).to_numpy(float)
    ta, ya = ty[ok], anom[ok]
    i, j = np.triu_indices(n, 1)
    pair = np.sort((ya[j] - ya[i]) / (ta[j] - ta[i]))
    var_s = n * (n - 1) * (2 * n + 5) / 18 * (n / f["n_eff"])
    z, npair = stats.norm.ppf(1 - alpha / 2), len(pair)
    lo = pair[int(np.clip(np.floor((npair - z * np.sqrt(var_s)) / 2), 0, npair - 1))]
    hi = pair[int(np.clip(np.ceil((npair + z * np.sqrt(var_s)) / 2), 0, npair - 1))]
    out.update(sen_per_decade=10 * float(np.median(pair)), sen_ci_low=10 * float(lo), sen_ci_high=10 * float(hi))

    # 3) display only: Hamed-Rao MK, fixed lag 3, only when (nearly) gap-free
    out["p_hamed_rao_lag3"] = np.nan
    if ok.mean() > 0.95:
        a = pd.Series(anom).interpolate(limit=1, limit_area="inside").to_numpy()
        a = a[np.isfinite(a)]
        try:
            out["p_hamed_rao_lag3"] = float(mk.hamed_rao_modification_test(a, lag=3).p)
        except Exception:
            pass

    # 5) Weatherhead et al. 1998: years needed to detect the current slope (constant 3.3 unverified)
    r1, slope = f["r1"], f["slope"]
    out["years_needed"] = (float((3.3 * f["sigma"] / abs(slope) * np.sqrt((1 + r1) / (1 - r1))) ** (2 / 3))
                           if slope else np.inf)
    mean = float(np.nanmean(y))
    out["pct_of_mean_per_decade"] = 100 * 10 * slope / mean if mean > 0 else np.nan
    t0, t1 = ty[ok][0], ty[ok][-1]
    level0 = mean - slope * (ty[ok].mean() - t0)
    out["pct_change_over_record"] = float(100 * slope * (t1 - t0) / level0) if level0 > 0 else np.nan
    out["signal_to_noise"] = abs(slope) * out["record_years"] / f["sigma"] if f["sigma"] > 0 else np.nan
    return out


def analyze(wide: pd.DataFrame, units: dict | None = None, breaks: dict | None = None,
            alpha: float = ALPHA) -> pd.DataFrame:
    """One row per variable. BH across the variables tested together, on the AR(1) p-value."""
    from statsmodels.stats.multitest import multipletests

    rows = []
    for vid in wide.columns:
        r = {"id": vid, "units": (units or {}).get(vid, "")}
        r.update(trend_report(wide[vid], (breaks or {}).get(vid, ()), alpha))
        rows.append(r)
    df = pd.DataFrame(rows)
    df["q_fdr"] = np.nan
    if "p_ar1" in df and df["p_ar1"].notna().any():
        ok = df["p_ar1"].notna()
        df.loc[ok, "q_fdr"] = multipletests(df.loc[ok, "p_ar1"].astype(float), method="fdr_bh")[1]

    def verdict(r):
        if r.get("too_short") is True or pd.isna(r.get("q_fdr")):
            return "Too short to tell"
        rising = r["slope_per_decade"] > 0
        sen_agrees = r["sen_ci_low"] > 0 if rising else r["sen_ci_high"] < 0
        if r["q_fdr"] < alpha and sen_agrees:
            return "Clear rise" if rising else "Clear fall"
        if r["q_fdr"] < alpha:
            return "Likely change, but the two methods disagree"
        more = r["years_needed"] - r["record_years"]
        if np.isfinite(more) and 1 <= more <= 50:
            return (f"No clear trend yet "
                    f"(check back around {int(round(int(str(r['last'])[:4]) + more))})")
        return "No clear trend yet"

    df["verdict"] = df.apply(verdict, axis=1)
    if "robust_to_breaks" in df:  # say so whenever the answer flips with or without the known instrument steps
        flips = (df["robust_to_breaks"] == False) & ~df["verdict"].str.contains("not robust")  # noqa: E712
        df.loc[flips, "verdict"] += " (answer changes depending on how the known instrument change is handled)"
    df["rank_score"] = np.where(df["verdict"].str.startswith("Clear"), df.get("signal_to_noise"), np.nan)
    return df.sort_values("rank_score", ascending=False, na_position="last", ignore_index=True)


def ols_ar1_map(Y: np.ndarray, ty: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorised primary method for maps. Y: (time, pixel) with no NaN, ty: decimal years.
    Returns slope per decade, p-value, lag-1 autocorrelation for every pixel."""
    X = _design(ty)
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    E = Y - X @ beta
    n, p = X.shape
    ss = (E ** 2).sum(0)
    r1 = np.clip(np.where(ss > 0, (E[1:] * E[:-1]).sum(0) / np.where(ss > 0, ss, 1), 0), 0, 0.99)
    dof = np.maximum(n * (1 - r1) / (1 + r1) - p, 1)
    se = np.sqrt(ss / dof * np.linalg.pinv(X.T @ X)[1, 1])
    with np.errstate(divide="ignore", invalid="ignore"):
        pval = 2 * stats.t.sf(np.abs(beta[1] / se), dof)
    return 10 * beta[1], pval, r1


SEASONS = {"DJF (winter)": (12, 1, 2), "MAM (spring)": (3, 4, 5), "JJA (summer)": (6, 7, 8),
           "SON (autumn)": (9, 10, 11)}
MIN_YEARS = 10


def season_series(s: pd.Series, months: tuple) -> pd.Series:
    """One value per year: the mean over `months`, only for years where every one of those months exists.
    December counts toward the following year's winter (DJF 2010 = Dec 2009, Jan 2010, Feb 2010)."""
    s = _to_monthly(s).dropna()
    mon = np.asarray(s.index.month)
    wraps = (12 in months) and (1 in months)
    yr = np.asarray(s.index.year) + ((mon == 12) & wraps).astype(int)
    keep = np.isin(mon, months)
    sel = pd.Series(s.to_numpy(float)[keep], index=pd.Index(yr[keep], name="year"))
    g = sel.groupby(level=0)
    out = g.mean()[g.count() == len(months)]
    return out


def season_trend(s: pd.Series, months: tuple, alpha: float = ALPHA) -> dict:
    """Trend of a seasonal mean (one value per year), with the same memory adjustment and Sen agreement check."""
    a = season_series(s, months)
    n = len(a)
    out = {"years": n, "first_year": int(a.index.min()) if n else None, "last_year": int(a.index.max()) if n else None}
    if n < MIN_YEARS:
        out["verdict"] = "Too short to tell"
        return out
    t = a.index.to_numpy(float)
    y = a.to_numpy(float)
    X = np.column_stack([np.ones(n), t - t.mean()])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ beta
    r1 = min(max(_lag1(e), 0.0), 0.99)
    ne = n * (1 - r1) / (1 + r1)
    dof = max(ne - 2, 1.0)
    se = float(np.sqrt((e ** 2).sum() / dof / ((t - t.mean()) ** 2).sum()))
    tcrit = stats.t.ppf(1 - alpha / 2, dof)
    slope = float(beta[1])
    p = float(2 * stats.t.sf(abs(slope / se), dof)) if se > 0 else np.nan
    p_naive = float(stats.linregress(t, y).pvalue)
    i, j = np.triu_indices(n, 1)
    pair = np.sort((y[j] - y[i]) / (t[j] - t[i]))
    var_s = n * (n - 1) * (2 * n + 5) / 18 * (n / ne)
    z, npair = stats.norm.ppf(1 - alpha / 2), len(pair)
    lo = pair[int(np.clip(np.floor((npair - z * np.sqrt(var_s)) / 2), 0, npair - 1))]
    hi = pair[int(np.clip(np.ceil((npair + z * np.sqrt(var_s)) / 2), 0, npair - 1))]
    rising = slope > 0
    sen_agrees = lo > 0 if rising else hi < 0
    out.update(slope_per_decade=10 * slope, ci_low=10 * (slope - tcrit * se), ci_high=10 * (slope + tcrit * se),
               p=p, p_ttest=p_naive, lag1_autocorr=r1, n_eff=ne, sen_per_decade=10 * float(np.median(pair)),
               sen_ci_low=10 * float(lo), sen_ci_high=10 * float(hi), mean=float(y.mean()),
               pct_of_mean_per_decade=100 * 10 * slope / y.mean() if y.mean() > 0 else np.nan, series=a)
    if p < alpha and sen_agrees:
        out["verdict"] = "Clear rise" if rising else "Clear fall"
    elif p < alpha:
        out["verdict"] = "Likely change, but the two methods disagree"
    else:
        out["verdict"] = "No clear trend yet"
    return out


def region_area_km2(shape) -> float:
    """Area of an outline in km2 (equal-area projection, EPSG:6933). Converts mm of water to volume:
    rate_mm_per_yr * area_km2 * 1e-6 = km3/yr (1 km3 of water = 1 Gt)."""
    import geopandas as gpd

    return float(gpd.GeoSeries([shape], crs=4326).to_crs(6933).area.iloc[0] / 1e6)


def buffer_km(shape, km: float):
    """Outline grown by `km` kilometres (measured in a projection centred on the region)."""
    if not km:
        return shape
    import geopandas as gpd
    from shapely.geometry import box as sbox

    c = shape.representative_point()
    g = gpd.GeoSeries([shape], crs=4326).to_crs(f"+proj=laea +lat_0={c.y} +lon_0={c.x} +datum=WGS84 +units=m")
    return g.buffer(km * 1000).to_crs(4326).iloc[0].buffer(0).intersection(sbox(-180, -90, 180, 90))


# Benchmarks (scripts/benchmarks.py) show GRACE averages inside an outline recover 0.64-1.02x of published mass
# trends: GRACE's ~3-degree resolution leaks signal across the edge. A 100 km margin recovers it for isolated
# targets (NW India 0.85x, Caspian 1.11x) but double-counts where neighbours change too (Central Valley 1.9x,
# Greenland 1.46x). So neither number is "right" on its own; the tool reports both as a range.
LEAKAGE_MARGIN_KM = 100


def percent_change(s: pd.Series, breaks=()) -> float:
    """Change over the record from the fitted trend, as % of the fitted starting level (how the NO2 papers
    report, e.g. Krotkov et al. 2016). Only meaningful for amounts that start at zero (rain, NO2, AOD, snow)."""
    s = _to_monthly(s)
    ty = (s.index.year + (s.index.month - 0.5) / 12).to_numpy(float)
    y = s.to_numpy(float)
    ok = np.isfinite(y)
    if ok.sum() < 24:
        return np.nan
    f = _ols_ar1(ty, y, ok, breaks)
    t0, t1 = ty[ok][0], ty[ok][-1]
    level0 = np.nanmean(y) - f["slope"] * (ty[ok].mean() - t0)
    return float(100 * f["slope"] * (t1 - t0) / level0) if level0 > 0 else np.nan
