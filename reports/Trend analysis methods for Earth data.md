# Correct for memory before claiming any trend

The best approach for a single-region monthly NASA series of 15 to 45 years is the one IPCC AR6 uses. Fit an ordinary least-squares trend to the deseasonalized data and judge its significance with a **lag-1 autocorrelation (AR(1)) adjustment to the effective sample size** (Santer et al. 2008). Then confirm it with a robust Theil-Sen slope whose confidence interval gets the same memory correction. A trend counts as real only when both agree and it survives Benjamini-Hochberg across the variables. Memory handling dominates every other choice. Monthly anomalies are persistent (lag-1 autocorrelation of about 0.2 to 0.9, highest for GRACE storage and soil moisture), and tests that ignore this flag "trends" in pure noise 15% to 60% of the time instead of 5%. The team's pipeline is built on sound parts: anomalies, Sen slope, Hamed-Rao MK, BH-FDR, Weatherhead detectability, and a 10-year floor. It has four defects that make it overconfident. First, the displayed Theil-Sen 95% CI assumes independent data. Second, `hamed_rao_modification_test` with its default `lag=None` gives roughly twice the nominal false-positive rate. Third, `seasonal_test` is not memory-corrected and misaligns seasons when months are missing. Fourth, per-pixel maps inherit the Hamed-Rao problem, and BH cannot repair that afterwards. The fix is about 90 lines of BSD/MIT Python, given below. In a quick check it held the false-positive rate at 2% to 6% across the whole autocorrelation range.

## Ignoring autocorrelation is the one clearly wrong choice

The estimator matters little. What matters is the noise model behind the p-value. In Santer et al.'s synthetic test (AR(1) noise with a1 = 0.87, 252 months), unadjusted trend tests rejected a true null **more than 60% of the time** at a nominal 5%, while the effective-sample-size adjustment brought this to **about 6%** ([Santer et al. 2008](https://www.image.ucar.edu/idag/Papers/santer_IJoC_published_2008.pdf)). The original Mann-Kendall test fails the same way: its Type I error reaches **about 0.15 already at ρ = 0.3** ([Wang et al. 2020](https://www.frontiersin.org/journals/earth-science/articles/10.3389/feart.2020.00014/full)). The popular TFPW-Y prewhitening variant gives **60-100% false positives** at lag-1 autocorrelation of 0.85-0.9 ([Collaud Coen et al. 2020](https://amt.copernicus.org/articles/13/6945/2020/)). By contrast, slope-based and rank-based tests have broadly similar power when both are applied correctly ([Yue & Pilon 2004](https://scholarhub.vn/publication/A-comparison-of-the-power-of-the-i-t-i-test-Mann-Kendall-and-bootstrap-tests-for-trend-detection-Une-comparaison-de-la-puissance-des-tests-i-t-i-de-Student-de-Mann-Kendall-et-du-bootstrap-pour-la-d%C3%A9tection-de-tendance/626ff67b-22ed-482c-9b9e-5a454adf7fa7)). So the parametric-versus-nonparametric debate is second order.

The team's own libraries show the problem directly. A 1,000-replicate no-trend simulation in the project's virtualenv (pymannkendall 1.4.3, scipy 1.18.1) found that at n = 120 and φ = 0.5, `theilslopes` CIs excluded zero **25.2%** of the time and `linregress` rejected **25.8%** of the time. Hamed-Rao rejected 16.6% with the default lag and 9.3% with `lag=3` ([PyPI pymannkendall](https://pypi.org/project/pymannkendall/); [PyPI scipy](https://pypi.org/project/scipy/)). The scipy CI is Sen's (1968) eq. 2.6 built on the independent-data MK variance, so it rejects exactly as often as the uncorrected MK test ([SciPy theilslopes docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.theilslopes.html)). The default-lag Hamed-Rao problem is a known open bug. Sen detrending biases sample autocorrelations negative, so spurious negative lags get included and the false-positive rate comes out at "roughly 2x the nominal rate" ([pyMannKendall issue #41](https://github.com/mmhs013/pyMannKendall/issues/41)). A separate fix for negative variances that produce NaN p-values is merged on GitHub but has not been released since January 2023 ([issue #29](https://github.com/mmhs013/pyMannKendall/issues/29)).

I ran a 200-replicate check of the recipe below in the same environment, with no true trend. It shows the intended behaviour. The AR(1)-adjusted OLS test held size near nominal everywhere. The memory-corrected Sen CI stayed close behind. Hamed-Rao with `lag=3` drifted upward at high persistence, and the uncorrected methods failed badly.

| n months, φ | AR(1)-adjusted OLS | Sen CI, n/n_eff corrected | Hamed-Rao lag=3 | Plain OLS t-test | scipy Sen CI (iid) |
|---|---|---|---|---|---|
| 180, 0.3 | 0.050 | 0.055 | 0.070 | 0.165 | 0.160 |
| 180, 0.6 | 0.055 | 0.070 | 0.090 | 0.305 | 0.330 |
| 180, 0.85 | 0.060 | 0.095 | 0.240 | 0.550 | 0.530 |
| 480, 0.6 | 0.050 | 0.055 | 0.085 | 0.365 | 0.360 |
| 480, 0.85 | 0.020 | 0.030 | 0.175 | 0.535 | 0.545 |

Two honest caveats apply. The AR(1) adjustment is known to overestimate the effective sample size slightly, which makes it "too liberal" when n_eff is small ([Santer et al. 2008](https://www.image.ucar.edu/idag/Papers/santer_IJoC_published_2008.pdf)). And if the noise has long-term persistence rather than AR(1) memory, every AR(1)-based test "greatly overstate[s]" significance, although the trend magnitude itself stays well determined ([Cohn & Lins 2005](https://pubs.usgs.gov/publication/70027303)). That risk is concentrated in GRACE storage and soil moisture. Those variables should carry a "may reflect slow natural swings" caveat rather than a heavier test, because with 180-540 points the Hurst exponent is too poorly constrained to correct for reliably.

## Ranked recommendation for this tool

The ranking below follows the evidence above and what the tool needs: one headline number, one defensible verdict, and a story students can follow ("two methods agree").

| Rank | Method | Role in the tool | Why |
|---|---|---|---|
| 1 | OLS trend + annual/semiannual harmonics (+ known instrument steps), AR(1) effective-sample-size SE (Santer 2008) | **Primary rate, CI and p-value** | IPCC AR6 method ([AR6 Fig. 2.11](https://www.ipcc.ch/report/ar6/wg1/figures/chapter-2/figure-2-11)); near-nominal size to φ ≈ 0.87; closed form, so it vectorizes to maps; handles gaps by regressing on real time |
| 2 | Theil-Sen slope with rank CI using MK variance × n/n_eff | **Robust agreement check**; headline slope for IMERG, OMI NO2, AOD | Resists skew and spikes; same memory correction, so the two methods are comparable |
| 3 | Hamed-Rao MK, `lag=3`, on gap-free series | Optional rank-test display | Better than default lag but still 9-24% size at φ ≥ 0.6; show it, do not let it decide |
| 4 | GLSAR / SARIMAX(1,0,0) with trend regressor | Validation of rank 1 in tests | Equivalent noise model, slightly more efficient; statsmodels 0.15 works ([PyPI statsmodels](https://pypi.org/project/statsmodels/)) |
| Avoid | Plain OLS t-test, original MK, scipy's default Sen CI, TFPW-Y alone, Newey-West with default bandwidth, `seasonal_test` as a significance arbiter | Teaching foil at most | Oversized; Newey-West "can have empirical size far above nominal" under strong dependence ([Lazarus et al.](https://discovery.ucl.ac.uk/10160486/1/har_JBES_v8.pdf)) |

Three methods were considered and ranked lower. The best-supported Mann-Kendall prewhitening schemes are TFPW-WS and 3PW (which requires both PW and TFPW-Y to reject, with a VCTFPW slope), implemented in the BSD-licensed `mannkendall` package ([Collaud Coen et al. 2020](https://amt.copernicus.org/articles/13/6945/2020/); [PyPI mannkendall](https://pypi.org/project/mannkendall/)). That package has been dormant since 2022 and adds complexity without beating rank 1. Hirsch-Slack seasonal Kendall is robust only up to ARMA φ ≈ 0.6 ([USGS record](https://www.usgs.gov/publications/a-nonparametric-trend-test-seasonal-data-serial-dependence)), and splitting the data by month widens CIs about fourfold ([Collaud Coen et al. 2020](https://amt.copernicus.org/articles/13/6945/2020/)). A moving-block bootstrap Sen CI is attractive in principle, but my first trial with block length about n^(1/3) rejected 13-25% of no-trend series. Short blocks cannot capture monthly persistence, so I replaced it with the analytic n/n_eff correction. The `arch` package's stationary bootstrap with Politis-White block length is a permissive-license option for a later version ([arch LICENSE](https://github.com/bashtage/arch/blob/main/LICENSE.md)).

## A one-day recipe in about 90 lines of permissive Python

Dependencies are numpy and pandas (BSD), scipy (BSD-3), statsmodels (BSD-3) and pymannkendall (MIT). There is nothing GPL, so avoid `pyleoclim` (GPL-3) and do not link R's `trend` (GPL-3) or `modifiedmk` (AGPL-3). Those two are fine for generating reference values offline ([libraries survey: PyPI pyleoclim](https://pypi.org/project/pyleoclim/); [CRAN trend](https://cran.r-project.org/package=trend); [CRAN modifiedmk](https://cran.r-project.org/package=modifiedmk)). I ran this code in the project venv. On 30-year synthetic series it runs in about 1 second per variable and produced the size table above.

```python
import numpy as np, pandas as pd
from scipy import stats
import pymannkendall as mk
from statsmodels.stats.multitest import multipletests

MIN_MONTHS = 120

def _lag1(e):
    """Lag-1 autocorrelation on a regular monthly grid that may contain NaN."""
    a, b = e[:-1], e[1:]
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok] - np.nanmean(e), b[ok] - np.nanmean(e)
    return float(np.sum(a * b) / np.nansum((e - np.nanmean(e)) ** 2))

def _design(ty, breaks):
    w = 2 * np.pi * ty
    cols = [np.ones_like(ty), ty - ty.mean(), np.sin(w), np.cos(w), np.sin(2 * w), np.cos(2 * w)]
    cols += [(ty >= b).astype(float) for b in breaks]
    return np.column_stack(cols)

def trend_report(s, breaks=(), alpha=0.05):
    """s: pd.Series on a monthly DatetimeIndex (gaps as NaN or missing rows).
    breaks: decimal years of documented product changes, e.g. (2018.42,) for GRACE-FO."""
    s = s.asfreq("MS")                                   # regular grid, gaps become NaN
    ty = (s.index.year + (s.index.month - 0.5) / 12).to_numpy(float)
    y = s.to_numpy(float); ok = np.isfinite(y); n = int(ok.sum())
    if n < MIN_MONTHS:
        return {"verdict": "Too short to test", "months": n}

    # 1) PRIMARY: OLS trend + annual/semiannual harmonics (+ known steps), AR(1)-adjusted (Santer et al. 2008)
    X = _design(ty[ok], breaks); p = X.shape[1]
    beta, *_ = np.linalg.lstsq(X, y[ok], rcond=None)
    e = np.full_like(y, np.nan); e[ok] = y[ok] - X @ beta
    r1 = max(_lag1(e), 0.0)
    ne = n * (1 - r1) / (1 + r1)
    dof = ne - p
    xt = X[:, 1]
    se = np.sqrt(np.nansum(e ** 2) / max(dof, 1) / np.sum(xt ** 2))
    tcrit = stats.t.ppf(1 - alpha / 2, max(dof, 1))
    slope = beta[1]                                       # units per year
    p_ar1 = 2 * stats.t.sf(abs(slope / se), max(dof, 1))
    se_naive = np.sqrt(np.nansum(e ** 2) / (n - p) / np.sum(xt ** 2))
    p_naive = 2 * stats.t.sf(abs(slope / se_naive), n - p)  # teaching only: "ignores memory"

    # 2) ROBUST CHECK: Sen slope on anomalies; rank-based CI (Sen 1968) with the
    #    Mann-Kendall variance inflated by n/n_eff, the same AR(1) memory correction as step 1
    month = s.index.month
    anom = (s - s.groupby(month).transform("mean")).to_numpy(float)
    ta, ya = ty[ok], anom[ok]
    i, j = np.triu_indices(n, 1)
    pair = np.sort((ya[j] - ya[i]) / (ta[j] - ta[i]))
    sen = float(np.median(pair))
    var_s = n * (n - 1) * (2 * n + 5) / 18 * (n / ne)
    z = stats.norm.ppf(1 - alpha / 2); N = len(pair)
    lo_b = pair[int(np.clip(np.floor((N - z * np.sqrt(var_s)) / 2), 0, N - 1))]
    hi_b = pair[int(np.clip(np.ceil((N + z * np.sqrt(var_s)) / 2), 0, N - 1))]

    # 3) RANK CHECK: Hamed-Rao MK with a fixed small lag, only on (near) gap-free series
    p_hr = np.nan
    if ok.mean() > 0.95:
        a = pd.Series(anom).interpolate(limit=1, limit_area="inside").to_numpy()
        a = a[np.isfinite(a)]
        p_hr = float(mk.hamed_rao_modification_test(a, lag=3).p)

    # 4) Weatherhead et al. (1998) years needed (verify constants against the paper)
    sigma_n = float(np.nanstd(e, ddof=p))
    yrs = (3.3 * sigma_n / abs(slope) * np.sqrt((1 + r1) / (1 - r1))) ** (2 / 3) if slope else np.inf

    return dict(months=n, years=(ty[ok][-1] - ty[ok][0]), slope_per_decade=10 * slope,
                ci_low=10 * (slope - tcrit * se), ci_high=10 * (slope + tcrit * se),
                p_ar1=p_ar1, p_naive=p_naive, r1=r1, n_eff=ne, short_memory_flag=ne < 30,
                sen_per_decade=10 * sen, sen_ci_low=10 * lo_b, sen_ci_high=10 * hi_b,
                p_hamed_rao_lag3=p_hr, years_to_detect=yrs,
                pct_of_mean_per_decade=100 * 10 * slope / np.nanmean(y) if np.nanmean(y) > 0 else np.nan)

def analyze_place(series_by_var, breaks_by_var=None, alpha=0.05):
    rows = {v: trend_report(s, (breaks_by_var or {}).get(v, ())) for v, s in series_by_var.items()}
    df = pd.DataFrame(rows).T
    tested = df["p_ar1"].notna() if "p_ar1" in df else pd.Series(False, index=df.index)
    df["q_bh"] = np.nan
    if tested.any():
        df.loc[tested, "q_bh"] = multipletests(df.loc[tested, "p_ar1"].astype(float), method="fdr_bh")[1]
    def verdict(r):
        if pd.isna(r.get("q_bh")): return "Too short to test"
        agree = (r.sen_ci_low > 0) if r.slope_per_decade > 0 else (r.sen_ci_high < 0)
        if r.q_bh < alpha and agree:
            return "Clear rise" if r.slope_per_decade > 0 else "Clear fall"
        if r.q_bh < alpha:
            return "Likely change, methods disagree"
        return f"Not yet distinguishable from natural ups and downs (~{r.years_to_detect:.0f} yr needed)"
    df["verdict"] = df.apply(verdict, axis=1)
    return df
```

The design choices each follow a specific finding. The trend is fitted jointly with harmonics on real decimal time rather than on interpolated data. That matters for GRACE, whose mission gap runs from about July 2017 to May 2018 ([Qian et al. 2024](https://www.mdpi.com/2072-4292/16/19/3693)). Rodell et al. interpolated only isolated missing months, to keep the calendar-month climatology balanced ([Rodell et al. 2018](https://pmc.ncbi.nlm.nih.gov/articles/PMC6077847)). Interpolating across the whole gap would invent observations. For complete records the joint fit gives essentially the same slope as the team's anomaly-then-fit approach. `breaks` adds step terms at documented product changes. A level shift can raise the years needed to detect a trend by **50% or more** ([Weatherhead et al. 1998](https://impacts.ucar.edu/en/publications/factors-affecting-the-detection-of-trends-statistical-considerati/)). Run each series with and without steps, and label the trend "not robust to known instrument changes" if its sign or verdict flips.

A per-dataset breaks table is short. GRACE needs a step at the June 2018 GRACE-FO start. For OMI NO2, the row anomaly began in June 2007 and eventually affected about half the rows ([Torres et al. 2018](https://espo.nasa.gov/atom/node/79579)), so filter flagged rows before averaging. Selecting well-performing rows cut US trend uncertainty by up to a factor of 3 ([EGU25-19924](https://meetingorganizer.copernicus.org/EGU25/EGU25-19924.html)). MERRA-2 retains observing-system discontinuities, most notably the 1998 AMSU-A introduction ([UCAR CDG MERRA-2](https://climatedataguide.ucar.edu/climate-data/nasas-merra2-reanalysis); [GMAO](https://gs6101-gmao.gsfc.nasa.gov/science-snapshots/merra-2-global-precipitation-time-series)). IMERG needs a caveat banner rather than a step. Its lead developer says "IMERG is not a Climate Data Record" and its roughly 20-year record "is really not sufficient for studies of long-term trends", and points users to GPCP ([UCAR CDG IMERG](https://climatedataguide.ucar.edu/climate-data/gpm-global-precipitation-measurement-mission)). Report precipitation as percent of mean per decade, which the recipe returns.

For per-pixel maps, use the rank-1 method because it is closed form and vectorizes across all pixels at once. Theil-Sen needs about n²/2 pairwise slopes per pixel ([SciPy docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.theilslopes.html)). For gap-free grids (MERRA-2, GLDAS, IMERG):

```python
def ols_ar1_map(Y, ty):                       # Y: (time, pixel), ty: decimal years
    X = _design(ty, ()); beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    E = Y - X @ beta; n, p = X.shape
    r1 = np.clip((E[1:] * E[:-1]).sum(0) / (E ** 2).sum(0), 0, 0.99)
    dof = np.maximum(n * (1 - r1) / (1 + r1) - p, 1)
    se = np.sqrt((E ** 2).sum(0) / dof / (X[:, 1] ** 2).sum())
    return 10 * beta[1], 2 * stats.t.sf(np.abs(beta[1] / se), dof)   # per decade, p
```

Apply BH to the map's p-values separately from the per-place family. Wilks recommends BH for gridded maps and shows that with strong spatial correlation it becomes conservative. In that case, **α_FDR = 0.10 yields roughly a 5% field-level test** ([Wilks 2016](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)). Use 0.10 for smooth fields (temperature, AOD) and 0.05 for precipitation, which decorrelates faster ([Ventura et al. 2004](https://www.stat.berkeley.edu/~paciorek/files/jclim/vent.etal.2004.pdf)). In his worked example, naive per-pixel p < 0.05 produced an achieved FDR of **0.55**, meaning a majority of the stippled pixels were spurious. Fade or hatch pixels that fail BH, and if none pass, say so rather than showing uncorrected stippling.

## Where the current pipeline is right, and what to change

Most of the architecture holds up. Each change is small and local to `earthpull/trends.py` and `earthpull/trendmap.py`.

| Component | Verdict | Change |
|---|---|---|
| Calendar-month anomalies | Right for complete series | For gappy series (GRACE, OMI), fit trend + harmonics jointly on real time; never interpolate the 2017-18 gap |
| `theilslopes` slope | Right as estimator | Keep; preferred headline for skewed IMERG, NO2, AOD |
| `theilslopes` 95% CI | **Wrong under autocorrelation** | Replace with the n/n_eff-corrected rank CI, or with the rank-1 AR(1) CI. The current CI excludes zero ~25-33% of the time on trendless φ=0.5-0.6 noise |
| `hamed_rao_modification_test()` defaults | **Oversized (~2x)** | Pass `lag=3`; feed gap-free data (its detrend step misaligns time when NaNs are dropped, per the installed source); treat NaN p as "not computable"; demote from verdict-maker to display |
| `seasonal_test` cross-check | **Not a valid check** | It assumes independent seasons with no memory correction, and `trends.py` calls it on `s.values` after `dropna()`, so any missing month shifts every later value into the wrong season. Drop it, or replace with a per-season (DJF/JJA) trend display |
| `linregress` OLS t-test | Fine as a labeled foil | Show as "what you'd get ignoring memory" (30-55% false alarms at φ ≥ 0.6) or remove |
| BH-FDR across variables | Right | Keep q = 0.05, apply it to the AR(1) p-value, show raw p and q side by side; keep per-place and per-map families separate; Holm as "strict mode" |
| Weatherhead years-to-detect | Right idea, matches the formula in the notes | Take σ_N and φ from the harmonic-fit residuals on the regular grid (current φ is computed on the compressed, gap-dropped series); also report for a reference trend size, since the observed slope is noisy; verify the 3.3 constant against [the paper](https://statistics.fas.harvard.edu/files/statistics-2/files/xlm_jgeophysres103-d14atmo_17149-17161_1998.pdf) |
| 10-year minimum | Reasonable floor | Keep; add an n_eff < 30 "short memory-adjusted record" flag and dataset caveats (IMERG, GRACE) |
| Per-pixel maps | **Local tests invalid** | BH assumes each local test has correct size ([Wilks 2016](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)); switch to `ols_ar1_map`, which is also far faster than per-pixel Hamed-Rao |

The verdict logic also needs one conceptual fix. Today the verdict rests on the Hamed-Rao q-value while the page shows an iid Sen CI. A student can therefore see a "Clear rise" whose interval crosses zero, or the reverse. In the recipe, the CI, the p-value and the BH q all come from the same memory-corrected model, and the Sen check uses the same n_eff, so the numbers on screen cannot contradict each other.

## Telling students what the numbers mean

The statistical work is wasted if the wording overclaims. Lead with magnitude and range ("+0.27 °C per decade, 95% range 0.22 to 0.33"). Give evidence strength in words paired with numbers. Laypeople in 24 countries read IPCC likelihood words as closer to 50% than intended, and adding numeric ranges helped but did not cure this ([Budescu et al. 2014, ANU summary](https://iceds.anu.edu.au/research/stories/does-language-impact-climate-scepticism)). The ASA's guidance is not to treat "not statistically significant" as evidence of absence, and to avoid the bare phrase "statistically significant" ([Wasserstein, Schirm & Lazar 2019](https://doi.org/10.1080/00031305.2019.1583913)). So a failed test should read "not yet distinguishable from natural ups and downs; at this noise level you'd need about N years", never "no trend". Wilks likewise warns that "significant at the 95% level" is non-standard and that a p-value is not the probability that the null is true ([Wilks 2016](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)). Two cheap visuals help. A LOESS overlay shows whether the line is a fair summary, since IPCC AR5 notes there is "no a priori physical reason" for linearity and that sub-period trends can even flip sign ([IPCC AR5 WG1 Ch. 2](https://www.ipcc.ch/site/assets/uploads/2017/09/WG1AR5_Chapter02_FINAL.pdf)). A trend-versus-start-year plot makes that sensitivity visible. If the team wants IPCC vocabulary, AR6 quotes 90% "very likely" ranges ([AR6 SPM](https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_SPM.pdf)), so either switch to 90% intervals or keep 95% and avoid IPCC likelihood words.

## Conclusion

For this tool, accuracy depends less on picking a clever test than on making one noise model drive every number on the screen. The AR(1) effective-sample-size correction is simple enough to explain to a high-school student ("neighbouring months are not independent, so 360 months count as fewer"). It matches what IPCC does, and it makes the maps fast instead of slow. The biggest remaining unknown is long-memory behaviour in GRACE storage and soil moisture, where any short-memory test is optimistic. The right response there is plain-language humility rather than a heavier test. Two items to verify before demo day: the exact Weatherhead constants, since the researchers could not extract them from the PDF, and the AR6 supplementary-material details of the Santer adjustment. Add one unit test that compares `trend_report` against statsmodels `GLSAR` on a fixed synthetic series, to catch regressions.
