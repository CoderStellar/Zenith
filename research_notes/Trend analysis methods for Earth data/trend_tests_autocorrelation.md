# Trend estimators and significance tests for autocorrelated, seasonal monthly Earth-science series

Scope: monthly regional means, 15-45 yr (n = 180-540), lag-1 autocorrelation (r1) about 0.2-0.8. Labels used below: "Cited Findings" were checked in the linked source during this session. "Inferences" are my own reasoning or background knowledge that I did NOT verify in a source this session. Several key primary PDFs (Santer 2000 JGR, Weatherhead 1998, IPCC figure pages, MDPI Atmosphere 2024) returned HTTP 403, so some numbers come from abstracts or search snippets. Those are flagged.

## Q1. Type I error and power of the candidate methods under lag-1 autocorrelation (OLS t-test, OLS + effective sample size, HAC/Newey-West, GLS-AR(1), MK variants, prewhitening, seasonal Kendall, block bootstrap)

### Takeaway
Ignoring autocorrelation is the one clearly wrong choice. In a monthly AR(1) setup with a1 = 0.87 and n = 252, unadjusted trend tests rejected more than 60% of the time at nominal 5%. The AR(1) effective-sample-size adjustment brought this down to about 6%. Among the Mann-Kendall family, the original MK and TFPW-Y fail to control Type I error as r1 rises. Plain prewhitening (PW) controls Type I error but loses power and biases the slope. The best-supported nonparametric options are TFPW-WS, VCTFPW or 3PW, and seasonal Kendall with the Hirsch-Slack correction.

### Cited Findings
**OLS, plain versus effective-sample-size (Santer) adjustment**
- Santer et al. (2008) compute the effective sample size following Santer et al. (2000) and substitute ne - 2 for nt - 2 in the standard error of the OLS slope. In their RSS tropical T2LT example (r1 = 0.884, nt = 252 months), ne ≈ 16, and the adjusted standard error is "over four times larger" than the unadjusted one — [Santer et al. 2008, IJoC](https://www.image.ucar.edu/idag/Papers/santer_IJoC_published_2008.pdf)
- Synthetic test in the same paper: AR(1) with a1 = 0.87, 252-month series, 1000 realizations, paired-trend test. With adjusted standard errors, rejection rates at nominal 5/10/20% were about 6/11/21%. Without the adjustment they "consistently exceed 60, 65, and 72%" — [Santer et al. 2008](https://www.image.ucar.edu/idag/Papers/santer_IJoC_published_2008.pdf)
- Santer et al. (2008) also say that "the use of an AR-1 model for calculating ne tends to overestimate the true effective sample size (Zwiers and von Storch, 1995)", which makes their test "too liberal". They also note that higher-order AR models are hard to estimate reliably from 20-30 yr records with high autocorrelation — [Santer et al. 2008](https://www.image.ucar.edu/idag/Papers/santer_IJoC_published_2008.pdf)
- Santer et al. (2000, JGR 105 D6) "employ two methods to account for temporal autocorrelation effects" in layer-average temperature trends. I could not open the full text (403), so their Monte Carlo numbers are not verified here — [Santer et al. 2000 (NOAA ARL copy)](https://www.arl.noaa.gov/documents/JournalPDFs/SanterEtal.JGR2000.pdf)

**HAC / Newey-West**
- Tests built on Newey-West standard errors "can have empirical size far above nominal size if the errors exhibit substantive temporal dependence". Small bandwidths give biased long-run variance estimates and large size distortions. Large bandwidths reduce size distortion but increase variance. Kiefer-Vogelsang fixed-b asymptotics are more accurate in finite samples. The Vogelsang-Franses (bandwidth = T) trend test shows "very little size distortion" with comparable power, according to McKitrick's climate application. That evidence comes mainly from the method's proponents. Source: search snippets of [McKitrick, robust measurement](https://www.rossmckitrick.com/uploads/4/8/0/8/4808045/robustmeasurement.pdf), [Vogelsang & Franses, common trend slopes](https://cae.economics.cornell.edu/commontrends.pdf), and [Lazarus, Lewis, Stock, Watson, HAR inference](https://discovery.ucl.ac.uk/10160486/1/har_JBES_v8.pdf)

**Original Mann-Kendall under AR(1)**
- Monte Carlo study: trend plus AR(1) noise, n = 50-400, 1,000-10,000 replicates, α = 0.05. MK Type I error rises with ρ and reaches about 0.15 already at ρ = 0.3. For n = 100, the variance of the standardized Z statistic rises from 1 to about 13.2 as ρ goes from 0 to 0.9. Positive ρ also reduces power for weak trends — [Wang et al. 2020, Front. Earth Sci. 8:14](https://www.frontiersin.org/journals/earth-science/articles/10.3389/feart.2020.00014/full)
- In the same study, without autocorrelation and with a fixed slope-to-noise setting, MK power was about 0.98/0.8/0.6/0.4 for n = 400/200/100/50. Power depends on slope, noise variance and length, not on length alone — [Wang et al. 2020](https://www.frontiersin.org/journals/earth-science/articles/10.3389/feart.2020.00014/full)

**Prewhitening family (PW, TFPW-Y, TFPW-WS, VCTFPW, 3PW)**
- Collaud Coen et al. (2020, AMT 13:6945) compared 5 prewhitening methods on 7 atmospheric datasets. Higher lag-1 autocorrelation increases Type I errors and biases the Sen slope. Prewhitening increases Type II errors (lowers power) — [Collaud Coen et al. 2020](https://amt.copernicus.org/articles/13/6945/2020/)
- With ak1 = 0.85-0.9, TFPW-Y gives 60-100% false positives. With ak1 = 0.8-0.85, it gives at least 40% (empirical comparison against PW as reference, not a pure simulation) — [Collaud Coen et al. 2020](https://amt.copernicus.org/articles/13/6945/2020/)
- For decadal trends with PW as the reference, MK, TFPW-Y and VCTFPW show 32-47% false positives, while TFPW-WS shows under 2% — [Collaud Coen et al. 2020](https://amt.copernicus.org/articles/13/6945/2020/)
- The paper cites simulations (Zhang & Zwiers 2004; Wang et al. 2015) showing that TFPW-WS (Wang & Swail 2001 iterative method) restores low Type I error without losing power — [Collaud Coen et al. 2020](https://amt.copernicus.org/articles/13/6945/2020/)
- Recommendations: prewhiten only when ak1 is significant. Use 3PW (PW and TFPW-Y both required for significance, VCTFPW for the slope) or TFPW-WS for significance. Do not use MK, TFPW-Y alone or VCTFPW to judge significance. Do not report the sign of non-significant slopes. Use the open-source "mannkendall" library — [Collaud Coen et al. 2020](https://amt.copernicus.org/articles/13/6945/2020/); [mannkendall library](https://mannkendall.github.io/about.html)
- Sheoran et al. 2024 (Atmosphere 15:1159), AR(1) simulations, reported only via abstract and search snippet (full text 403). The original series and TFPW-Y "failed to control Type-I error as ρ1 increased". VCTFPW and their new DPWMT kept Type I error below 0.05 for large samples. VCTFPW lost power at ρ1 ≥ 0.7 because it underestimates the slope. "Apart from TFPW-Y, all PW methods resulted in weak power of the test for weak trends and small samples." — [Sheoran et al. 2024, Atmosphere](https://mdpi.com/2073-4433/15/10/1159)
- Faye et al. (2014): among PW, TFPW and modified TFPW, TFPW had the highest power (Type I error not reported in the snippet) — search snippet only, [Atmosphere 2024 DOAJ record](https://doaj.org/article/97fa180c0eba48bbb0f470cadbd349ba)

**Variance-correction MK (Hamed-Rao 1998)**
- Hamed-Rao detrends the series, then computes an effective sample size from significant serial correlation coefficients (the R implementation uses only significant lags) — [modifiedmk mmkh docs](https://search.r-project.org/CRAN/refmans/modifiedmk/html/mmkh.html)
- An MDPI study reports that one effective-sample-size correction "could remove the lag-1 autocorrelation significantly, but the Type-I error after correction was still much higher than the significance level". The snippet does not say which correction this was — search snippet of [Sheoran et al. 2024](https://mdpi.com/2073-4433/15/10/1159)
- "Yue & Wang 2004" is ambiguous. The indexed 2004 Yue & Wang items are replies to comments by Zhang & Zwiers and by Bayazit & Önöz on prewhitening. The effective-sample-size MK variance correction is usually cited as Yue & Wang 2004 (Water Resour. Manage.), but I did not confirm that here — [ASCE VCTFPW paper listing](https://ascelibrary.com/doi/10.1061/%28ASCE%29HE.1943-5584.0001234)

**Seasonal Kendall and Hirsch-Slack (1984)**
- Hirsch & Slack (1984, WRR 20(6):727-732): Monte Carlo experiments show the serial-dependence-robust seasonal Kendall test is robust in Type I error "except when the data have strong long-term persistence (e.g., ARMA(1,1) monthly processes with ϕ > 0.6) or short records (~5 years)". Without serial correlation it is less powerful than the original seasonal Kendall — [USGS publication record](https://www.usgs.gov/publications/a-nonparametric-trend-test-seasonal-data-serial-dependence)

**Bootstrap and slope-versus-rank tests**
- Yue & Pilon (2004, Hydrol. Sci. J. 49:21-37) compared t-test, MK, bootstrap-slope and bootstrap-MK by Monte Carlo. The t-test and BS-slope have the same power, MK and BS-MK have the same power, and the two families differ depending on the distribution — abstract via [scholarhub listing](https://scholarhub.vn/publication/A-comparison-of-the-power-of-the-i-t-i-test-Mann-Kendall-and-bootstrap-tests-for-trend-detection-Une-comparaison-de-la-puissance-des-tests-i-t-i-de-Student-de-Mann-Kendall-et-du-bootstrap-pour-la-d%C3%A9tection-de-tendance/626ff67b-22ed-482c-9b9e-5a454adf7fa7)
- The block-bootstrap MK (Önöz & Bayazit 2012) resamples predetermined blocks to retain the memory structure. The R docs recommend about 2000 replicates — [modifiedmk package](https://search.r-project.org/CRAN/packages/modifiedmk/modifiedmk.pdf)

**GLS / AR(1) regression (Weatherhead et al. 1998)**
- Weatherhead et al. (1998, JGR 103 D14:17149) give formulae for the number of years needed to detect a trend. It increases with noise variance and with the noise lag-1 autocorrelation φ. For typical values, detecting 5%/decade (ozone) needs about 10 to more than 20 years. Level shifts can lengthen this by 50% or more — abstract via [UCAR impacts record](https://impacts.ucar.edu/en/publications/factors-affecting-the-detection-of-trends-statistical-considerati/)
- Detecting ozone recovery is expected to take 15-45 years for most regions (Weatherhead et al. 2000) — [UCAR record](https://impacts.ucar.edu/en/publications/detecting-the-recovery-of-total-column-ozone/)

### Inferences
- Background knowledge, not verified this session: Weatherhead's widely used forms are σ_ω ≈ σ_N n^(-3/2) sqrt((1+φ)/(1-φ)) for the trend standard error (n in years) and n* ≈ [3.3 σ_N/|ω0| · sqrt((1+φ)/(1-φ))]^(2/3) for 90% detection probability at the 5% level. The tool could compute and report "years needed to detect" with these. Check them against the PDF before use.
- Background knowledge, not verified: the Santer form is ne = n(1 - r1)/(1 + r1), with r1 taken from OLS residuals. At r1 = 0.8 and n = 252, ne ≈ 28. Because r1 estimated from short series is biased low, this method gets liberal when ne is small (roughly below 20-30). That is consistent with the Zwiers & von Storch caveat quoted above. With r1 = 0.2-0.6 and n ≥ 180, it should be close to nominal, consistent with the about 6% rejection Santer found even at a1 = 0.87.
- GLS with AR(1) errors (Prais-Winsten / Cochrane-Orcutt / ML) and OLS with an ne correction should behave similarly for AR(1) noise. GLS is slightly more efficient. Both inherit the same small-sample bias in estimated φ. I found no direct head-to-head numbers this session.
- Newey-West with the default automatic bandwidth is the weakest of the autocorrelation-aware parametric options for n = 180-540 with r1 ≥ 0.6, given the documented over-rejection. Fixed-b or Vogelsang-Franses versions fix much of this.
- Seasonal Kendall on raw monthly values handles the seasonal cycle without needing anomalies. With deseasonalized anomalies, any of the methods above can be applied directly. Hirsch-Slack's ϕ > 0.6 failure threshold overlaps the upper end of the team's r1 range, for example GRACE TWS and soil moisture anomalies, which are highly persistent.

### Gaps
- No exact rejection-rate tables were retrieved for Hamed-Rao, Yue-Wang, GLS-AR(1) or Newey-West at n = 180-540 and r1 = 0.2-0.8. The MDPI, Santer 2000, Weatherhead and IPCC pages returned 403.
- Mudelsee 2019 (Earth-Science Reviews) on block-bootstrap trend CIs was not retrieved. Its coverage-accuracy claims are unverified here.
- Hess, Iyer & Malm (2001, Atmos. Environ. 35:5211) compared 7 linear trend methods by simulation on seasonal, autocorrelated environmental data. Only the bibliographic record was found, so the methods and results are unverified — [scilit record](https://www.scilit.net/publications/90ab4ad130856298e4dd1485ee3bc0b2)
- Bayazit & Önöz (2007) "To prewhiten or not to prewhiten" and Hamed's follow-up were not found in search. Their argument, that PW is unnecessary for large samples and big trends but reduces power, is background knowledge only.

## Q2. Theil-Sen slope: CI under autocorrelation, efficiency and robustness versus OLS

### Takeaway
The standard Sen CI is built from percentiles of the pairwise slopes using a normal quantile and the MK variance. It assumes independence, so under positive autocorrelation it is too narrow unless the MK variance is inflated (Hamed-Rao or ne) or the CI is block-bootstrapped. Sen slope estimates from MK and TFPW-Y are biased high under strong autocorrelation, PW is biased low, and VCTFPW is the recommended near-unbiased version.

### Cited Findings
- Collaud Coen et al. (2020) define Sen-slope confidence limits from percentiles of the pairwise slopes, using the standard normal distribution (90% default) — [Collaud Coen et al. 2020](https://amt.copernicus.org/articles/13/6945/2020/)
- Slope bias, cited in Collaud Coen et al.: MK and TFPW-Y overestimate the slope by up to 80% for 10-yr series and 21% for 20-yr series under strong autocorrelation (Hardison et al. 2019). PW underestimates it at all strengths, and MK and TFPW-WS overestimate it for periods under 200 yr (Zhang & Zwiers 2004). TFPW-Y and VCTFPW slopes differ by 200-1000% at the highest ak1. VCTFPW is recommended as the unbiased slope, at least for series under 30 yr — [Collaud Coen et al. 2020](https://amt.copernicus.org/articles/13/6945/2020/)
- Monthly segmentation in seasonal MK gives confidence limits about 4 times wider than no segmentation and about 2 times wider than meteorological seasons. Meteorological seasons gave more homogeneous trends than monthly segments — [Collaud Coen et al. 2020](https://amt.copernicus.org/articles/13/6945/2020/)
- Aggregating from monthly to 3-month or annual means reduces ak1 sharply. At annual aggregation, ak1 is mostly not significant, but CIs widen — [Collaud Coen et al. 2020](https://amt.copernicus.org/articles/13/6945/2020/)
- The openair R package (widely used for air-quality trends, such as NO2) offers a Theil-Sen CI with a block bootstrap for autocorrelated data (Künsch 1989), with block length n^(1/3). The code comments call this "an ongoing development" — [openair TheilSen docs](https://search.r-project.org/CRAN/refmans/openair/html/TheilSen.html); [openair book](https://bookdown.org/david_carslaw/openair/sections/trend-analysis/theil-sen.html)
- A 2026 EGUsphere supplement compares a basic Theil-Sen CI with a block-bootstrap Theil-Sen CI for satellite-sonde drift. The two disagree on at least one case. The snippet suggests the significance call changes, but the direction is ambiguous — [EGUsphere-2025-6473 AC1 supplement](https://egusphere.copernicus.org/preprints/2026/egusphere-2025-6473/egusphere-2025-6473-AC1-supplement.pdf)

### Inferences
- Background knowledge, not verified: for Gaussian iid errors, the asymptotic relative efficiency of Theil-Sen to OLS slope is about 0.95. Its breakdown point is about 29%. Under heavy-tailed or skewed errors such as precipitation and AOD spikes, Sen is more efficient than OLS. Sen is the safer default estimator for IMERG precipitation, OMI NO2 and AOD. For MERRA-2 temperature, OLS and Sen give nearly the same result.
- A defensible Sen CI for autocorrelated monthly data would be either (a) a moving-block or stationary bootstrap of the detrended residuals added back to the trend, with blocks long enough to cover the decorrelation time (n^(1/3) ≈ 6-8 months for n = 180-540, which may be too short when r1 ≥ 0.7), or (b) the rank-based CI with the MK variance inflated by the Hamed-Rao n/n* factor. Neither has verified coverage numbers from this session.

### Gaps
- I found no formal coverage study quantifying how far the naive Sen CI under-covers at given r1 and n.
- I found no source this session quantifying Sen versus OLS efficiency under autocorrelation specifically.

## Q3. Head-to-head simulation studies (parametric GLS-AR(1) versus nonparametric MK variants)

### Takeaway
Direct parametric-versus-nonparametric comparisons on climate-like data are sparse in what I could retrieve. The available ones (Yue & Pilon 2004; Wang et al. 2020; Collaud Coen 2020; Sheoran 2024) agree on several points. Slope-based and rank-based tests have broadly similar power. The handling of autocorrelation matters far more than the parametric-versus-rank choice. No MK prewhitening variant is perfect at both Type I control and power when r1 ≥ 0.7.

### Cited Findings
- t-test and bootstrap-slope have equal power, MK and bootstrap-MK have equal power, and relative power across the two families depends on the error distribution — [Yue & Pilon 2004](https://scholarhub.vn/publication/A-comparison-of-the-power-of-the-i-t-i-test-Mann-Kendall-and-bootstrap-tests-for-trend-detection-Une-comparaison-de-la-puissance-des-tests-i-t-i-de-Student-de-Mann-Kendall-et-du-bootstrap-pour-la-d%C3%A9tection-de-tendance/626ff67b-22ed-482c-9b9e-5a454adf7fa7)
- MK and Spearman's rho have practically indistinguishable power (Yue, Pilon & Cavadias 2002, J. Hydrol.) — [same listing](https://scholarhub.vn/publication/A-comparison-of-the-power-of-the-i-t-i-test-Mann-Kendall-and-bootstrap-tests-for-trend-detection-Une-comparaison-de-la-puissance-des-tests-i-t-i-de-Student-de-Mann-Kendall-et-du-bootstrap-pour-la-d%C3%A9tection-de-tendance/626ff67b-22ed-482c-9b9e-5a454adf7fa7)
- Wang et al. 2020 recommend raising α from 0.05 to 0.1 or lengthening records. Required lengths are much shorter for temperature and humidity than for runoff and precipitation — [Wang et al. 2020](https://www.frontiersin.org/journals/earth-science/articles/10.3389/feart.2020.00014/full)
- Prewhitening for Pettitt and other tests gives "rejection rates reasonably close to the nominal values" (SERRA 2016) — snippet of [Stoch. Environ. Res. Risk Assess. 2016](https://link.springer.com/content/pdf/10.1007/s00477-015-1041-5.pdf)

### Inferences
- Ranking for this tool's use case (inference, combining all of the above):
  1. OLS (or Sen) slope on deseasonalized monthly anomalies, with significance from an AR(1)-adjusted standard error (Santer ne, equivalent to the IPCC approach) or from GLS-AR(1). It is transparent, matches IPCC practice, and gives near-nominal size for r1 up to about 0.87 at n = 252. Add a caution flag when ne < about 20-30.
  2. Seasonal Kendall with the Hirsch-Slack correction, or MK with TFPW-WS / 3PW, plus a VCTFPW Sen slope. Use this as the robust check for precipitation, NO2 and AOD.
  3. Moving-block bootstrap as a cross-check.
  - Avoid: the plain OLS t-test, the original MK, TFPW-Y alone, and Newey-West with a default automatic bandwidth.
- For students, a good message is "two methods agree". Report significance only if the AR(1)-adjusted OLS/GLS and the robust MK variant both reject. This mirrors the 3PW logic of Collaud Coen.

### Gaps
- I did not retrieve a single study running GLS-AR(1), Santer-ne, Hamed-Rao, TFPW-WS and the block bootstrap on the same simulated monthly series at n = 180-540. Hess et al. (2001) is the most likely candidate, but its full text was not accessible.

## Q4. What IPCC AR6 WG1, NOAA, WMO and NASA GISS use

### Takeaway
IPCC AR6 WG1 Chapter 2 uses linear (OLS) trends with significance assessed "following AR(1) adjustment after Santer et al. (2008)", which is the effective-sample-size method, and marks non-significant grid cells with "×". I did not find official NOAA, WMO or GISS documentation of a specific significance test this session.

### Cited Findings
- AR6 WG1 Figure 2.11 caption: significance is assessed following AR(1) adjustment after Santer et al. (2008), with "×" marking non-significant trends (HadCRUT5, 1900-1980 and 1981-2020) — search snippet of [IPCC AR6 WG1 Fig. 2.11](https://www.ipcc.ch/report/ar6/wg1/figures/chapter-2/figure-2-11) (direct fetch returned 403) and [CEDA figure data record](https://catalogue.ceda.ac.uk/uuid/033cd690801741c9bc745b8da55faef4)
- A Technical Summary figure assesses significance "with autoregressive AR(1) model correction", denoted by stippling — search snippet of [IPCC TS CCBox 1 figure](https://www.ipcc.ch/report/ar6/wg1/figures/technical-summary/ts-ccbox-1-figure-1/)
- AR6 Cross-Chapter Box 2.3 Figure 1 compares the two trend-fitting metrics used in AR5 and AR6 (linear trend versus difference of period means) — [IPCC CCBox 2.3 fig](https://ipcc.ch/report/ar6/wg1/figures/chapter-2/ccbox-2-3-figure-1)
- The method details are in the chapter's Supplementary Material (IPCC_AR6_WGI_Chapter_02_Supplementary_Material.pdf, Table 2.SM.1), referenced by the CEDA records — [CEDA](https://catalogue.ceda.ac.uk/uuid/f3515388768344bfb2be0521f82388be)
- A 2015 Climatic Change analysis of NASA GISS and NOAA monthly global temperatures found that "autocorrelation in the temperature time series is non-negligible" and used resampling for significance. This is an academic analysis, not agency practice — [Climatic Change 2015](https://link.springer.com/10.1007/s10584-015-1495-y)

### Inferences
- Background knowledge, not verified: AR6 reports trend ranges as 90% (very likely) intervals, and AR5 Chapter 2 also used OLS with an AR(1) ne adjustment. NOAA NCEI "Climate at a Glance" reports OLS trends per decade without a published autocorrelation-adjusted significance test. GISS's published uncertainty work (Lenssen et al. 2019) concerns data uncertainty, not trend tests. WMO State of the Climate reports mostly cite values without a stated test. Verify each before stating it in the tool.
- For defensibility in front of judges, "IPCC AR6 method: OLS trend with AR(1)-adjusted effective sample size (Santer et al. 2008), 90% CI" is the strongest single citation.

### Gaps
- The AR6 Chapter 2 SM text (confidence level, exact ne formula, whether ARMA(1,1) was used for any indicator) was not retrieved.
- No NOAA NCEI or WMO guidance document on trend significance was found. WMO-No. 1269 (Guidelines on Climate Normals) and the WMO climate-data guidance were not checked.

## Q5. Long-term persistence (Hurst; Cohn & Lins 2005; Hamed 2008): when does it matter for 20-40 yr records?

### Takeaway
Under LTP (FARIMA / Hurst) noise, AR(1)-based tests still overstate significance. Cohn & Lins show this "greatly" with FARIMA Monte Carlo. Trend magnitude is robust, but significance depends critically on the null model. For 15-45 yr monthly regional series, LTP is hard to identify and costly in power. It is most relevant for hydrological storage variables such as GRACE TWS, soil moisture and some runoff-like series.

### Cited Findings
- "Monte Carlo experiments employing FARIMA models indicate that trend tests which fail to consider LTP greatly overstate the statistical significance of observed trends when LTP is present". Trend magnitude can be determined "with little ambiguity", but significance "is less certain because significance depends critically on the null hypothesis" — [Cohn & Lins 2005, GRL 32 L23402](https://pubs.usgs.gov/publication/70027303); [PDF](https://webarchive.library.unt.edu/web/20090506203433/http:/water.usgs.gov/osw/pubs/Naturally_Trendy-Cohn-Lins_GRL_2005.pdf)
- Hirsch-Slack seasonal Kendall loses Type I control under "strong long-term persistence (e.g., ARMA(1,1) monthly processes with ϕ > 0.6)" — [USGS record](https://www.usgs.gov/publications/a-nonparametric-trend-test-seasonal-data-serial-dependence)
- In total ozone, some latitude bands show long-range correlated noise that makes trend uncertainty larger than AR(1) models predict — search snippet of [core.ac.uk ozone LRC paper](https://core.ac.uk/download/16395653.pdf)

### Inferences
- With n = 180-540 monthly values, the Hurst exponent H is poorly constrained, with a confidence interval of maybe ±0.1 or more (background knowledge, unverified). LTP-aware tests such as Hamed 2008 cut power heavily. The practical approach is to use AR(1)/ARMA(1,1) as the default, mention LTP as a caveat, and for GRACE (about 20 yr, with a 2017-2018 gap) and soil moisture, describe trends as "consistent with natural variability" unless they are very large.
- ARMA(1,1) is a reasonable middle ground. The AR6 "fit residuals follow ARMA(1,1)" remark, from a related AR6 methods paper seen only as a search snippet, supports this.

### Gaps
- Hamed 2008 (J. Hydrol., "Trend detection in hydrologic data: the Mann-Kendall trend test under the scaling hypothesis") was not retrieved. I have no numbers on how much its LTP correction inflates variance for n = 180-540.
- No study was found that quantifies at what H value AR(1)-adjusted tests become badly liberal for 20-40 yr monthly records.
