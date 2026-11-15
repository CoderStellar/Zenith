# Python libraries for the trend pipeline: licenses, maintenance, correctness

How to read this: "Verified (source)" means checked in PyPI JSON metadata, the GitHub REST API, a LICENSE file, official docs, or the **installed source code in `/home/lazerwild/Desktop/nasaspaceapps/.venv`** (pymannkendall 1.4.3, statsmodels 0.15.0, scipy 1.18.1, numpy 2.5.4). "Verified (local test)" means I ran it in that venv on 2026-11-15; those scripts are not online sources, so their claims cite the installed package's PyPI page plus a description of the test. Everything else is marked as inference. Metadata was retrieved on 2026-11-15.

## Summary table: method -> library -> license -> maintenance -> caveats

| Method | Library / function | License (verified) | Latest release / activity | Known bugs or caveats |
|---|---|---|---|---|
| MK + Hamed-Rao modified MK | `pymannkendall.hamed_rao_modification_test` | MIT | 1.4.3, 2023-01-14 (last PyPI upload). Last commit 2025-03-22. 12 open issues/PRs | Negative var_s gives NaN p (#29): fixed on GitHub but **not released**. Default `lag=None` gives roughly 2x the nominal false-positive rate (#41, confirmed locally). NaN handling misaligns the detrend step. Slope is per time step |
| Seasonal MK | `pymannkendall.seasonal_test` | MIT | same | Variance assumes the seasons are independent. NaNs are dropped per season (fine). `correlated_seasonal_test` ignores `alpha` (#36) and may be missing a variance term (#23) |
| Sen slope + CI | `scipy.stats.theilslopes` | BSD-3 | scipy 1.18.1, 2026-08-21 | CI is Sen (1968) eq. 2.6, which assumes independence. Under AR(1) it behaves exactly like the original MK test (oversized). `nan_policy='propagate'` is the default |
| Repeated-median slope | `scipy.stats.siegelslopes` | BSD-3 | same | No CI is returned |
| OLS t-test | `scipy.stats.linregress` | BSD-3 | same | Assumes iid errors |
| OLS + HAC SE | `statsmodels OLS.fit(cov_type="HAC")` | BSD-3-Clause | 0.15.0, 2026-08-27 | You must choose maxlags. Newey-West rule of thumb is 4 for n=240 |
| AR(1) error regression | `statsmodels GLSAR`, `SARIMAX(exog=t, order=(1,0,0))` | BSD-3-Clause | same | Works on 0.15 (tested) |
| STL / decomposition | `statsmodels.tsa.seasonal.STL`, `seasonal_decompose` | BSD-3-Clause | same | Works on 0.15 (tested) |
| FDR | `statsmodels.stats.multitest.multipletests(method="fdr_bh")` | BSD-3-Clause | same | Works on 0.15 (tested) |
| Granger | `grangercausalitytests(x, maxlag, addconst=True)` | BSD-3-Clause | same | **`verbose` kwarg removed in 0.15 (TypeError)** |
| Block bootstrap CI | `arch.bootstrap.MovingBlockBootstrap` / `StationaryBootstrap` / `CircularBlockBootstrap`, `optimal_block_length` | PyPI: `NCSA`. GitHub: NOASSERTION (custom permissive text, no copyleft) | 9.0.0, 2026-11-11. Repo pushed 2026-11-14 | Not installed. License is permissive but non-standard; flag it for a reviewer if needed |
| MK alternative (MeteoSwiss) | `mannkendall` | BSD-3-Clause | 1.1.1, 2022-07-08. Repo `mannkendall/Python`, last push 2022-07-08 | Dormant |
| MK alternative (censored/irregular) | `MannKS` | MIT (deps: piecewise-regression MIT, seaborn BSD) | 0.7.1, 2026-11-14. Very active. 2 stars, single author | Young. 0.6 was a "correctness release" (results changed). Has block bootstrap |
| Gridded MK | `xarrayMannKendall` | MIT (PyPI license text; repo MIT) | 1.4.5, 2023-03-16. Repo last push 2023-03-16 | Dormant. Uses the Yue-Wang modification; check whether it shares the issue #41 problem (not verified) |
| Change points | `ruptures` | BSD-2-Clause | 1.1.10 (GitHub release 2025-09-10), 1.1.11rc1 on PyPI 2025-11-27. Repo pushed 2026-10-06, 2.1k stars | Penalised segmentation. Gives no significance test |
| Homogeneity tests | `pyhomogeneity` (Pettitt, SNHT, Buishand) | MIT | 1.1, 2020-05-04. Repo last push 2022-04-16 | Dormant. Same author as pymannkendall |
| Bayesian change point | PyPI `changepoint` (promised-ai) | MIT | 0.4.0, 2025-10-20 | This is **not** a port of R's `changepoint` |
| Skill / metrics on grids | `xskillscore` | Apache-2.0 | 0.0.29, 2026-02-18. Repo active | Has no trend test (inference) |
| Climate indices | `xclim` | Apache-2.0 | 1.0.0, 2026-11-05. Active | Could not confirm an MK or Theil-Sen indicator |
| **Avoid (GPL)** | `pyleoclim` | **GPL-3.0** | 1.3.1b0 | Do not depend on it |
| Reference only (R) | `modifiedmk` 1.6 (**AGPL-3**), `trend` 1.1.10 (**GPL-3**) | copyleft | CRAN | Fine for generating reference values offline. Do not ship or link them |

---

## pymannkendall: release status, open correctness issues, missing values

### Takeaway
pymannkendall (MIT) is effectively unmaintained on PyPI: the last release is 1.4.3 from Jan 2023, and fixes merged in 2025 have not been released. Its Hamed-Rao test with the default `lag=None` gives too many false positives, and its NaN handling in the Hamed-Rao detrend step is internally inconsistent. Use `lag=3` (or a fixed small lag), drop NaNs yourself before calling, and treat a NaN p-value as "test failed".

### Cited Findings
- Latest PyPI version is 1.4.3, uploaded 2023-01-14, under the MIT license (classifier "OSI Approved :: MIT License") — [PyPI pymannkendall](https://pypi.org/project/pymannkendall/)
- GitHub repo: MIT, last push 2025-03-22, 293 stars, 12 open issues and PRs, not archived. The last commits merge PR #34 ("fixes issue 29") and PR #33 ("fixes issue #32"), both dated 2025-03-22 — [GitHub mmhs013/pyMannKendall](https://github.com/mmhs013/pyMannKendall)
- **Issue #29**: `hamed_rao_modification_test` can return a negative `var_s`, so z and p come out NaN. Reproductions include a 12-point series. The proposed fix is `abs(sni)`. On 2026-02-04 a user asked for a new release that includes the fix — [Issue #29](https://github.com/mmhs013/pyMannKendall/issues/29)
- **Issue #32**: `__acf` divides by `acov[0]`, which is 0 for a constant series, giving NaN or a warning. Fixed on GitHub, not released — [Issue #32](https://github.com/mmhs013/pyMannKendall/issues/32)
- **Issue #41** (2026-11-06, open): `yue_wang_modification_test` with the default `lag=None` rejects H0 about 47% of the time on white noise. A follow-up comment (2026-11-11) says `hamed_rao_modification_test` with `lag=None` also rejects at "roughly 2x the nominal rate". The stated cause: Sen detrending biases the sample autocorrelations negative, so spuriously significant negative lags get included — [Issue #41](https://github.com/mmhs013/pyMannKendall/issues/41)
- **Issue #36** (open): `correlated_seasonal_test` ignores `alpha` for `h` and `trend`. PR #38 ("Forward alpha in correlated_seasonal_test") is open and unmerged — [Issue #36](https://github.com/mmhs013/pyMannKendall/issues/36)
- **Issue #23** (open since 2022): the variance in `correlated_multivariate_test` may omit the first summation term of Hipel and McLeod (1994) Eq. 23.3.12 — [Issue #23](https://github.com/mmhs013/pyMannKendall/issues/23)
- **Issue #21** (open): the Sen slope uses index differences `(j - i)`, not time differences, so the slope is per sample, not per unit time — [Issue #21](https://github.com/mmhs013/pyMannKendall/issues/21)
- Issues #30 and #35 (open) report `np.float` use in `__preprocessing`. However, the installed 1.4.3 source uses `np.asarray(x).astype(float)` (checked locally), so this does not affect numpy 2.5 — [Issue #35](https://github.com/mmhs013/pyMannKendall/issues/35); local source `pymannkendall/pymannkendall.py` line 19
- Installed source, read directly (see [PyPI pymannkendall](https://pypi.org/project/pymannkendall/) for the package):
  - **Missing values:** `__missing_values_analysis(method='skip')` drops NaNs (`x[~np.isnan(x)]`). The MK S statistic is then computed on the compressed series. Order is preserved, so S is still valid, but autocorrelation lags are computed on the compressed series.
  - **Hamed-Rao NaN misalignment:** `slope, intercept = sens_slope(x_old)` uses the original indices (NaNs included, combined with `nanmedian`). The detrend, however, is `x_detrend = x - np.arange(1,n+1) * slope` on the NaN-dropped `x`, so the time index is wrong whenever there are gaps.
  - **Hamed-Rao lags:** `lag=None` sets `lag = n`, so every lag up to n-1 is screened at the `alpha` level. A user-supplied `lag=L` uses lags 1..L. The docstring notes that Hamed and Rao (1998) proposed using 3.
  - **Sen slope:** `sens_slope` uses `np.nanmedian` over pairwise slopes `(x[j]-x[i])/(j-i)` on the original indices, so NaNs are handled correctly there.
  - **Seasonal test:** `seasonal_test` pads the series to a multiple of `period` with NaN and reshapes it to (years, period). `multivariate_test` then drops NaNs **per season column** and sums S and Var(S) across seasons, so it assumes the seasons are independent.
  - **Ties:** Var(S) includes the standard tie correction. `Tau = s/(.5*n*(n-1))` (tau-a, no tie adjustment).
- Local simulation (1000 replicates, AR(1) Gaussian noise, no trend, p<0.05) — [PyPI pymannkendall](https://pypi.org/project/pymannkendall/) (package tested), [PyPI scipy](https://pypi.org/project/scipy/):

  | n, phi | original MK | HR `lag=None` | HR `lag=3` | HR NaN-p rate | theilslopes CI excludes 0 | OLS linregress |
  |---|---|---|---|---|---|---|
  | 30, 0.0 | 0.034 | 0.080 | 0.063 | 0.012 | 0.034 | 0.031 |
  | 30, 0.5 | 0.213 | 0.202 | 0.179 | 0.013 | 0.213 | 0.240 |
  | 120, 0.0 | 0.047 | 0.079 | 0.047 | 0.004 | 0.047 | 0.049 |
  | 120, 0.5 | 0.252 | 0.166 | 0.093 | 0.004 | 0.252 | 0.258 |

- Alternatives:
  - `mannkendall` (MeteoSwiss): BSD 3-Clause, 1.1.1 (2022-07-08). The repo moved to `mannkendall/Python`, last push 2022-07-08 — [PyPI mannkendall](https://pypi.org/project/mannkendall/), [GitHub mannkendall/Python](https://github.com/mannkendall/Python)
  - `MannKS`: MIT, 0.7.1 uploaded 2026-11-14. It supports irregular sampling, censored data, seasonal tests and a block bootstrap (`autocorr_method='block_bootstrap'`, since 0.2.0). Release 0.6.0 is described as a "correctness release, audited against the LWP-TRENDS R code and NADA", and 0.6.3 "corrects direct confidence interval indexing per Gilbert (1987) Eq. 16.8". Requirements: NumPy, Pandas ≥2.2, SciPy, Matplotlib, Seaborn, piecewise-regression — [PyPI MannKS](https://pypi.org/project/MannKS/), [GitHub README](https://github.com/LukeAFullard/MannKS)
  - MannKS dependency licenses: piecewise-regression 1.5.0 is MIT; seaborn is BSD — [PyPI piecewise-regression](https://pypi.org/project/piecewise-regression/), [PyPI seaborn](https://pypi.org/project/seaborn/)
  - The R packages are copyleft: CRAN `modifiedmk` 1.6 (2021-06-10) is AGPL-3, and CRAN `trend` 1.1.10 (2026-10-24) is GPL-3 — [CRAN modifiedmk](https://cran.r-project.org/package=modifiedmk), [CRAN trend](https://cran.r-project.org/package=trend)

### Inferences
- The table shows that no variant controls size well under AR(1) phi=0.5. HR with `lag=3` is the best of those tested at n=120 (9.3% against a nominal 5%). For monthly anomalies, which often have phi of 0.3 to 0.7, treat HR p-values as optimistic. Combining HR(`lag=3`) with a block-bootstrap CI or an AR(1)/GLS model is more defensible than HR with the default lag.
- Practical rules:
  - Call `mk.hamed_rao_modification_test(x[np.isfinite(x)], lag=3)` on gap-free data, or only when gaps are under about 5%.
  - Convert the slope with `slope*12` to get per-year values from monthly data.
  - Report `p=NaN` as "not computable".
- Optional patch: vendor the GitHub fix for #29 (`abs(sni)`), or pin to the GitHub commit. Pinning a git commit is quick but less reproducible. The library is MIT, so vendoring a single function is allowed if you keep the license notice.
- R `modifiedmk` or `trend` can be run once offline to produce reference values for a unit test. Do not add them as dependencies because of AGPL/GPL.
- MannKS looks careful but has a single maintainer, 2 stars and very frequent changes. For a one-day build, pin the exact version if you use it.

### Gaps
- I did not run MannKS, `mannkendall` or R reference values against pymannkendall.
- I did not inspect the merged GitHub fix diffs for #29 and #32.
- I found no published systematic validation of pymannkendall beyond its 2019 JOSS paper.

---

## statsmodels 0.15: HAC, GLSAR/SARIMAX, STL, multipletests, API changes

### Takeaway
statsmodels 0.15.0 (BSD-3-Clause, released 2026-08-27) supports all the planned calls. Local tests passed for OLS-HAC, GLSAR, SARIMAX with an exogenous trend, STL and `multipletests('fdr_bh')`. The one confirmed break is that `grangercausalitytests` no longer accepts `verbose`.

### Cited Findings
- statsmodels 0.15.0 was uploaded 2026-08-27, `license_expression: BSD-3-Clause` — [PyPI statsmodels](https://pypi.org/project/statsmodels/)
- Local checks of signatures and behaviour (statsmodels 0.15.0) — [PyPI statsmodels](https://pypi.org/project/statsmodels/):
  - Signature is `grangercausalitytests(x, maxlag, addconst=True)`. Passing `verbose=False` raises `TypeError: grangercausalitytests() got an unexpected keyword argument 'verbose'`.
  - Signatures are `GLSAR(endog, exog=None, rho=1, missing='none', hasconst=None, **kwargs)` and `multipletests(pvals, alpha=0.05, method='hs', maxiter=1, is_sorted=False, returnsorted=False)`.
  - The default `multipletests` method is `'hs'`, not BH, so pass `method="fdr_bh"` explicitly. Example: p=[.01,.02,.03,.5] gives reject [T,T,T,F] and adjusted p [.04,.04,.04,.5].
  - Simulated monthly series (n=240, AR(1) phi=0.6, true trend 0.05/yr), as a single example:

    | Model | Slope | Uncertainty |
    |---|---|---|
    | OLS-HAC, maxlags=4 | 0.0310 | 95% CI [0.0005, 0.0615], p=0.046 |
    | GLSAR (iterative) | 0.0307 | rho=0.43, SE 0.0178 |
    | SARIMAX(1,0,0) + exog trend | 0.0306 | p=0.097 |

### Inferences
- The Newey-West rule `floor(4*(n/100)**(2/9))` gives only 4 lags for n=240. With persistent AR(1) monthly anomalies, HAC is known to under-cover in small samples, and the example's narrower interval is consistent with that. That is one draw, not a coverage study. A parametric AR(1) model (GLSAR or SARIMAX) is the better comparison.
- Possible extras: `use_correction=True` in `cov_kwds`, or `kernel="bartlett"` (the default).

### Gaps
- I did not read the statsmodels 0.15 release notes or changelog, so other API changes are unverified.
- I did not verify which `cov_kwds` defaults changed in 0.15, if any.

---

## scipy theilslopes / siegelslopes CI, and block-bootstrap CI with arch

### Takeaway
`theilslopes` returns Sen's (1968) rank-based CI. It is built from the Mann-Kendall variance of S with tie corrections, which assumes independent observations. Under autocorrelation it is invalid and rejects exactly as often as the original MK test. For an autocorrelation-robust CI, use a moving or stationary block bootstrap: `arch` (permissive license, active) or a small hand-written numpy version.

### Cited Findings
- Docs: `low_slope` and `high_slope` are the bounds of the slope CI. `alpha` is the "confidence degree" (default 0.95), and 0.1 and 0.9 both mean a 90% CI. No CI is given for the intercept. The implementation "follows" Sen (1968). `method` is `'separate'` (default) or `'joint'`. `nan_policy` is `propagate` (default), `omit` or `raise`. The docs state no independence assumption — [SciPy theilslopes docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.theilslopes.html)
- Installed scipy 1.18.1 source (`scipy/stats/_correlation.py`) — [PyPI scipy](https://pypi.org/project/scipy/):
  - The comment reads "This implements (2.6) from Sen (1968)" with `sigsq = 1/18*(n(n-1)(2n+5) - Σ ties_x - Σ ties_y)`, which is the iid MK variance.
  - The CI is the order statistics of the sorted pairwise slopes at ranks `(N ± z*sigma)/2`.
  - The signature is `theilslopes(y, x=None, alpha=0.95, method='separate', *, axis=None, nan_policy='propagate', keepdims=False)`, so it is vectorised over `axis`. The decorator skips the dask backend ("no take_along_axis").
  - `siegelslopes` returns slope and intercept only, with no CI.
- Local test: with one NaN in the input, `theilslopes` returns all-NaN under the default `nan_policy` — [PyPI scipy](https://pypi.org/project/scipy/)
- arch metadata — [PyPI arch](https://pypi.org/project/arch/), [GitHub bashtage/arch](https://github.com/bashtage/arch):
  - PyPI: 9.0.0 uploaded 2026-11-11, `license_expression: NCSA`.
  - GitHub API: license NOASSERTION, repo pushed 2026-11-14, 1678 stars.
- arch LICENSE.md says "Copyright (c) 2017 Kevin Sheppard". It is a permissive license with conditions to retain notices and not use the authors' names for endorsement, and it has no copyleft clause — [arch LICENSE.md](https://github.com/bashtage/arch/blob/main/LICENSE.md)
- `arch.bootstrap.optimal_block_length` implements Politis and White (2004) with the Patton, Politis and White (2009) correction. It returns a DataFrame with `b_sb` (stationary bootstrap) and `b_cb` (circular block bootstrap) — [arch optimal_block_length docs](https://arch.readthedocs.io/en/latest/bootstrap/generated/arch.bootstrap.optimal_block_length.html)

### Inferences
- In the local simulation, the share of `theilslopes` CIs excluding 0 equals the original MK rejection rate in every cell (for example 0.252 vs 0.252 at n=120, phi=0.5). That confirms the CI inherits the iid assumption.
- Recommended snippet (arch API from my knowledge of arch; not run because arch is not installed):
  ```python
  from arch.bootstrap import StationaryBootstrap, optimal_block_length
  b = float(optimal_block_length(resid)["b_sb"].iloc[0])  # resid = anomalies - Sen fit
  bs = StationaryBootstrap(b, resid, seed=0)
  fit = slope*t + intercept
  boots = [stats.theilslopes(fit + r[0][0], t).slope for r in bs.bootstrap(1000)]
  lo, hi = np.percentile(boots, [2.5, 97.5])
  ```
  Bootstrapping the detrended residuals and adding back the fitted line keeps the trend intact. Resampling the raw series would destroy it.
- With no new dependency, a moving-block bootstrap with block length about `n**(1/3)` (roughly 5 to 6 for n=180) is about 10 lines of numpy. That is the "rule-of-thumb" block length, which is my inference and not from a source above.
- Use `nan_policy='omit'` explicitly on gappy data.

### Gaps
- I did not run arch, and did not run a coverage simulation of the block-bootstrap CI.
- I did not confirm whether the PyPI "NCSA" label is the author's declaration in `pyproject.toml`.

---

## Change-point and homogeneity libraries (non-GPL)

### Takeaway
ruptures (BSD-2, actively maintained) and pyhomogeneity (MIT, dormant since 2020) are both safe to use. pyhomogeneity provides the classical tests (Pettitt, SNHT, Buishand) with p-values. ruptures gives segmentations without significance.

### Cited Findings
- ruptures — [PyPI ruptures](https://pypi.org/project/ruptures/), [GitHub deepcharles/ruptures](https://github.com/deepcharles/ruptures):
  - BSD-2-Clause on both PyPI and GitHub.
  - Last stable GitHub release v1.1.10 (2025-09-10); PyPI also has 1.1.11rc1 (2025-11-27).
  - Repo pushed 2026-10-06, 2114 stars, 48 open issues and PRs.
- pyhomogeneity: MIT, version 1.1 (2020-05-04), repo last push 2022-04-16, 1 open issue. Same author as pymannkendall — [PyPI pyhomogeneity](https://pypi.org/project/pyhomogeneity/), [GitHub mmhs013/pyHomogeneity](https://github.com/mmhs013/pyHomogeneity)
- The PyPI package named `changepoint` is "A Bayesian change point library" from promised-ai. It is MIT, version 0.4.0 (2025-10-20), and its repo language is listed as Jupyter Notebook — [PyPI changepoint](https://pypi.org/project/changepoint/), [GitHub promised-ai/changepoint](https://github.com/promised-ai/changepoint)
- MIT: `changefinder` 0.5 — [PyPI changefinder](https://pypi.org/project/changefinder/)
- **GPL-3.0**: `pyleoclim` (it has paleoclimate trend and spectral tools). Avoid it — [PyPI pyleoclim](https://pypi.org/project/pyleoclim/)

### Inferences
- For a homogeneity flag such as an instrument or satellite change, `pyhomogeneity.pettitt_test(x)` is the simplest option. It is dormant but small. Its p-values are also iid-based, so autocorrelation inflates false detections, as with MK.
- `ruptures.Pelt(model="l2").fit(x).predict(pen=...)` needs a penalty choice, for example BIC-like `pen = 2*log(n)*sigma^2`.

### Gaps
- I did not check the pyhomogeneity issue tracker in detail, and did not verify the ruptures API in a local install.

---

## Vectorised trend maps over xarray grids

### Takeaway
The least-risk options are `scipy.stats.theilslopes(..., axis=...)`, or `xr.apply_ufunc` wrapped around a fixed-lag MK function, plus `xarray.polyfit` for OLS. xarrayMannKendall (MIT) is dormant since 2023. xskillscore and xclim (both Apache-2.0) are active, but I could not confirm that either has an MK or Theil-Sen trend function.

### Cited Findings
- xarrayMannKendall (dependencies: numpy and xarray, conda-forge package available) — [PyPI xarrayMannKendall](https://pypi.org/project/xarrayMannKendall/), [GitHub README](https://github.com/josuemtzmo/xarrayMannKendall):
  - MIT, 1.4.5 (2023-03-16), repo last push 2023-03-16, 2 open issues.
  - "computes linear trends over 2D and 3D arrays" with xarray parallelism, and cites the Yue and Wang (2004) effective-sample-size modification.
- xskillscore: Apache-2.0, 0.0.29 (2026-02-18), repo pushed 2026-11-13 — [PyPI xskillscore](https://pypi.org/project/xskillscore/)
- xclim: Apache-2.0, 1.0.0 (2026-11-05), repo pushed 2026-11-12 — [PyPI xclim](https://pypi.org/project/xclim/)
- easyclimate has an xarray `mk_test` (seasonal variant included) based on pymannkendall outputs. PyPI shows **no license metadata** for easyclimate 2026.8.1, so its license is unclear — [easyclimate mk_test docs](https://easyclimate.readthedocs.io/en/latest/technical/api/easyclimate/core/mk_test/index.html), [PyPI easyclimate](https://pypi.org/project/easyclimate/)
- `scipy.stats.theilslopes` accepts `axis` and `keepdims`, but not dask arrays — [SciPy theilslopes docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.theilslopes.html)

### Inferences
- Theil-Sen builds all pairwise slopes, about n²/2 per pixel. For n=240 months that is about 29k slopes per pixel, so chunk over space.
- Snippet:
  ```python
  def _ts(y):
      ok = np.isfinite(y)
      if ok.sum() < 120: return np.array([np.nan]*3)  # 10-year minimum
      r = stats.theilslopes(y[ok], t[ok])
      return np.array([r.slope, r.low_slope, r.high_slope])
  out = xr.apply_ufunc(_ts, da, input_core_dims=[["time"]], output_core_dims=[["stat"]],
                       vectorize=True, dask="parallelized", output_sizes={"stat":3},
                       output_dtypes=[float])
  ```
  `vectorize=True` loops in Python, which is slow but simple.
- Given issue #41, xarrayMannKendall's Yue-Wang implementation should be checked for unscreened all-lag ACF sums before it is trusted. Unverified.
- Use the easyclimate path only after its license is confirmed.

### Gaps
- I could not confirm whether xclim 1.0 has a trend or MK indicator; neither the docs search nor the API page turned one up.
- I did not inspect xarrayMannKendall's source.

---

## Weatherhead et al. (1998) years-to-detect: reference implementations

### Takeaway
I found no Python or R package that implements the Weatherhead et al. (1998) formula. It is short enough to implement directly from the paper.

### Cited Findings
- The paper (J. Geophys. Res. 103(D14), 17149-17161, 1998) gives formulas for the number of years needed to detect a trend. The number depends on the noise variance and autocorrelation, and level shifts can increase it by 50% or more. For typical values, detecting a 5%/decade trend takes from about 10 to more than 20 years — [Weatherhead et al. 1998 PDF](https://statistics.fas.harvard.edu/files/statistics-2/files/xlm_jgeophysres103-d14atmo_17149-17161_1998.pdf), [UCAR record](https://impacts.ucar.edu/en/publications/factors-affecting-the-detection-of-trends-statistical-considerati/)
- A web search for a Python implementation found none — [search context: pyMannKendall JOSS](https://joss.theoj.org/papers/10.21105/joss.01556)

### Inferences
- From my knowledge of the paper, not re-verified against the PDF text in this session:
  - The formula is `n* ≈ [ (3.3 σ_N / |ω0|) * sqrt((1+φ)/(1−φ)) ]^(2/3)` years.
  - `ω0` is the trend per year, `σ_N` is the standard deviation of the monthly noise (anomaly residuals), and `φ` is the lag-1 autocorrelation of the monthly noise.
  - The 3.3 constant corresponds to 90% probability of detection at the 5% level.
  - The paper also gives an uncertainty factor for n*, of the form `exp(±2*4/(3*sqrt(n)) * sqrt((1+φ)/(1−φ)))`.
- The report writer should check these constants and units against the PDF before stating them as fact.

### Gaps
- I did not extract the paper's equations from the PDF in this session.
- I found no reference implementation to cross-check against, including in R.
