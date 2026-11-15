# Multiple-testing control and reporting trend significance (per place and per map)

Verification legend used throughout:
- **[V-full]** = I read the primary full text this session (quotes are verbatim).
- **[V-abstract]** = verified from the abstract, a caption page, or a search excerpt of the primary source only.
- **[PK]** = from my prior knowledge of the source; NOT re-fetched this session (the publisher blocked automated access or I ran out of budget). The report writer should treat these as "likely correct, not verified here." The URL is the canonical location.

---

## 1. Wilks 2006 and Wilks 2016: what they recommend, alpha_FDR = 2 x alpha_global, robustness of BH to correlation

### Takeaway
Wilks (2016, BAMS) explicitly recommends Benjamini-Hochberg FDR control for gridded maps and says that for moderate-to-strong spatial correlation (typical of gridded atmospheric data) you should set alpha_FDR = 2 x alpha_global (for example 0.10 to get an approximately 0.05 field-level test), because BH becomes conservative, with achieved global levels about half the nominal level. Ventura et al. (2004) independently found plain BH still controls FDR under climate-like spatial correlation, and that the dependence-proof Benjamini-Yekutieli version is "too conservative to be useful."

### Cited Findings
**Wilks 2016, "The stippling shows statistically significant grid points" (BAMS 97(12):2263-2274, doi:10.1175/BAMS-D-15-00267.1).** Read from the author's AMS 2016 Annual Meeting manuscript of the same paper (the AMS journal site returned 403). [V-full, preprint]
- Survey: of 281 papers in *Journal of Climate* in the first half of 2014, 97 (34.5%) had maps described with some variant of "the stippling shows statistically significant grid points," while "only 3 of the 281 papers (1.1%) considered the effects of multiple testing on their scientific conclusions." — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- The key result on correlation (verbatim): achieved global levels "are approximately correct for small spatial correlations, but then decline fairly quickly and stabilize at about half the nominal levels. Thus the FDR procedure is robust to the effects of spatial correlation, yielding a somewhat conservative global test when the spatial correlation is moderate or strong ... for data grids exhibiting moderate to strong spatial correlation, approximately correct global test levels can be produced using the FDR procedure by choosing αFDR = 2αglobal." — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- Conclusions section (verbatim): "The usual strong spatial correlation encountered in gridded atmospheric data can be accommodated by choosing αFDR = 2αglobal." It also says FDR "should be adopted whenever the results of simultaneous multiple hypothesis tests are reported or interpreted." — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- Simulation setup: 3,720 gridpoints; eight spatial autocorrelation functions with e-folding distances from 0.1 x 10^3 km ("nearly spatially independent") to 10 x 10^3 km ("very strongly" correlated); the "realistic" case is an e-folding distance of 1.54 x 10^3 km (c = 0.42), which closely matches Northern Hemisphere 500-mb heights. Figure 4 caption: "For moderate and strong spatial correlation, approximately correct results can be achieved by choosing αFDR = 2αglobal." — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- Worked example (realistic correlation, 156 true signals out of 3,720): FDR at alpha_FDR = 0.10 rejected 150 tests, of which 6 were false (achieved FDR 0.04). The naive "p < 0.05 at each gridpoint" approach rejected 345, of which 189 were false: an achieved FDR of 0.55, "a majority of the nominally significant results are spurious!" — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- The Livezey-Chen counting procedure, without a correlation adjustment, is "very strongly permissive": it needs at least 208 local rejections (5.6%) for field significance at 0.05 under an independence assumption, but gives achieved global levels of 0.0907 and 0.3517 at e-folding distances of 0.2 and 1.54 x 10^3 km. — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- Temporal autocorrelation: because FDR is robust to spatial autocorrelation, serial correlation should be handled inside each local test (for example effective sample size or AR(1) adjustment). The method works "so long as the individual tests operate correctly (i.e., with proportion of true null hypotheses rejected close to the nominal test level α0)." — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- FDR doubles as a field-significance test: if no sorted p-value meets the BH criterion, the global null is not rejected, and the global test size is alpha_global = alpha_FDR (citing Wilks 2006). — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- The paper warns that p-values are not the probability that H0 is true, and that "significant at the 95% level" is non-standard terminology (footnote 1). — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)

**Wilks 2006, "On 'Field Significance' and the False Discovery Rate" (J. Appl. Meteor. Climatol. 45:1181-1189, doi:10.1175/JAM2404.1).** [V-abstract]
- The abstract says the FDR method gives a "more broadly applicable and generally more powerful field significance test than the conventional counting procedure," and that Walker's test and FDR are both robust to spatial dependence. It adds that using the minimum local p-value (the Walker test) is nearly equivalent to the slightly more powerful FDR-based global test. — [abstract via ScienceGate](https://next.sciencegate.app/document/10.1175/jam2404.1); [ResearchGate record](https://www.researchgate.net/publication/249603588_On_Field_Significance_and_the_False_Discovery_Rate)

**Ventura, Paciorek & Risbey 2004 (J. Climate 17:4343-4356).** [V-full]
- In simulations with spatial correlation like real climate data (GHCN station data and sea level pressure, n = 3,024 locations), plain BH ("FDR-Indep") "does control the proportion of falsely rejected hypotheses despite the violation of assumptions." The dependence-proof Benjamini-Yekutieli 2001 method ("FDR-General") "is too conservative to be useful." The authors recommend plain BH. — [Ventura et al. 2004](https://www.stat.berkeley.edu/~paciorek/files/jclim/vent.etal.2004.pdf)
- Under positive spatial correlation, BH's actual FDR stays below q, but "the tightness of the control degrades as spatial correlation increases, which in turn reduces the power." — [Ventura et al. 2004](https://www.stat.berkeley.edu/~paciorek/files/jclim/vent.etal.2004.pdf)
- They propose a modified BH that estimates the proportion of true alternatives *a* and runs BH at q/(1 - a). This is based on Genovese & Wasserman's bound, FDR <= (1 - a)q. They caution that the estimate of *a* is biased high under strong correlation, so FDR control is "not necessarily guaranteed" for the modified version. — [Ventura et al. 2004](https://www.stat.berkeley.edu/~paciorek/files/jclim/vent.etal.2004.pdf)
- Framing (abstract): "the field significance approach determines if a field as a whole is significant, a multiple testing procedure determines which particular tests are significant." — [Ventura et al. 2004](https://www.stat.berkeley.edu/~paciorek/files/jclim/vent.etal.2004.pdf)

**Benjamini & Hochberg 1995; Benjamini & Yekutieli 2001.** [PK]
- BH 1995 (JRSS-B 57:289-300) defines FDR as the expected proportion of false rejections among all rejections and gives the step-up rule p(i) <= (i/m)q. BY 2001 (Ann. Statist. 29:1165-1188) proves BH controls FDR under "positive regression dependence on a subset" (PRDS). For arbitrary dependence, it gives the version that divides q by sum_{i=1..m} 1/i (about ln m + 0.58), which is about 13 for m = 260,000. — [BH 1995](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x); [BY 2001](https://doi.org/10.1214/aos/1013699998)

### Inferences
- For the per-pixel map (hundreds to about 260,000 tests): use BH with alpha_FDR = 0.10 if you want to state "field significant at about 5%" for spatially smooth fields (temperature, NDVI, AOD, SST). Wilks's correlation regime is defined by e-folding distance (about 1,500 km is "realistic" for 500-mb height). Surface fields such as precipitation are less correlated (Ventura shows precipitation decorrelates faster than SLP), so for those, alpha_FDR = 2 x alpha_global may be slightly liberal. Choosing alpha_FDR = 0.05 is the safe default when the correlation regime is unknown.
- BY is not worth using: at m = 260,000 it would divide q by about 13, and Ventura shows it is impractically conservative.
- Wilks's FDR guarantee assumes each local test has the right size. If per-pixel Mann-Kendall or OLS tests ignore serial autocorrelation, local p-values are too small and no FDR rule fixes that. Use a pre-whitened or effective-sample-size Mann-Kendall, or OLS with an AR(1)-adjusted standard error, before BH.
- US states (about 50 tests) are less spatially correlated than pixels and few in number. Plain BH at q = 0.05 is reasonable there, and the 2x adjustment is not justified.

### Gaps
- I could not open the published BAMS version (403). The AMS conference manuscript is the same paper by the same author, but page numbers and minor wording may differ from the journal version.
- I did not quantify where "moderate" correlation starts on Wilks's Figure 4 axis. From the figure, achieved levels fall below nominal somewhere between e-folding distances of about 0.2 and 1 x 10^3 km, but the figure text did not extract cleanly.

---

## 2. Field significance vs local significance (Livezey & Chen 1983) and when to report each

### Takeaway
Local significance asks "is the trend at this pixel or variable real?" Field (global) significance asks "is there any real signal anywhere in the field, or could this many hits arise by chance?" Livezey and Chen (1983) introduced field significance, but the counting version has low power and is very sensitive to spatial correlation. BH-FDR answers both questions at once: it gives a field-level verdict and a list of local results in which the expected fraction of false hits is bounded.

### Cited Findings
- Wilks summarizes Livezey and Chen 1983 as a "meta-test" of the global null that all local nulls are true. "If a global null hypothesis cannot be rejected, one cannot conclude with adequate confidence that any of the individual local tests show meaningful violations." — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- Drawbacks of the counting approach (verbatim summary): it "lacks statistical power ... when the features to be detected occupy a small fraction of the domain," it "is very sensitive to the usual strong spatial correlation," and it needs elaborate Monte Carlo methods. Also, "even when the overall test results are strong enough to achieve field significance, many of the nominally significant gridpoint tests will have resulted from spurious local null hypothesis rejections." — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- The Walker test (reject the global null if the minimum p <= 1 - (1 - alpha0)^(1/N), roughly alpha0/N) is strict and has low power, but it is robust to dependence. — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- Ventura et al. argue that field significance alone does not say which locations are significant. A multiple-testing procedure does, and FDR results "are more easily interpretable." — [Ventura et al. 2004](https://www.stat.berkeley.edu/~paciorek/files/jclim/vent.etal.2004.pdf)
- Livezey & Chen 1983: "Statistical field significance and its determination by Monte Carlo techniques," Mon. Wea. Rev. 111:46-59. [PK for bibliographic details] — [doi:10.1175/1520-0493(1983)111<0046:SFSAID>2.0.CO;2](https://doi.org/10.1175/1520-0493(1983)111%3C0046:SFSAID%3E2.0.CO;2)

### Inferences
- For a map, report both levels in one line, for example: "Field test: a real trend exists somewhere in this region (FDR 10%, field level about 5%). Marked pixels: places where the trend passes FDR; we expect no more than about 1 in 10 marked pixels to be a fluke."
- If BH rejects nothing, the tool should say "No pixel passes the false-discovery check; the pattern you see could be noise." It should not show uncorrected stippling.
- Local patterns that look coherent are not evidence in themselves. Wilks warns that spurious rejections "may appear to be physically coherent structures because of the strong spatial autocorrelation."

### Gaps
- I did not read Livezey and Chen 1983 directly. The characterization above comes through Wilks and Ventura.

---

## 3. A handful of variables at one place (8-15 tests): BH, Holm, or no correction?

### Takeaway
No primary climate-statistics source found here addresses the 8-15-variable-at-one-place case directly; the following is my reasoning from the sources. BH is defensible and fits the exploratory, "which of these are worth a look" purpose. Holm controls the familywise error rate (FWER, the chance of even one false flag) and is the choice when any single false claim would be costly. Reporting raw p-values with no correction is acceptable only if each variable is a separately pre-specified question and the tool says so.

### Cited Findings
- FDR controls "a priori the expected proportion of falsely rejected tests out of all rejected tests," whereas most classical procedures control "for every test, the probability of detecting significance that does not really exist." — [Ventura et al. 2004 abstract](https://www.stat.berkeley.edu/~paciorek/files/jclim/vent.etal.2004.pdf)
- Ventura and Wilks both describe Bonferroni-type control (Walker test, about alpha/N) as too conservative for large fields. — [Ventura et al. 2004](https://www.stat.berkeley.edu/~paciorek/files/jclim/vent.etal.2004.pdf); [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- With alpha = 0.05 and N0 = 100 true nulls, the probability of at least one false rejection is 0.994. — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)
- Holm (1979, Scand. J. Statist. 6:65-70) is a step-down procedure that controls FWER under any dependence and is uniformly more powerful than Bonferroni. [PK] — [Holm 1979 (JSTOR)](https://www.jstor.org/stable/4615733)

### Inferences
- With 10 tests at 0.05 and no correction, the chance of at least one false flag is 1 - 0.95^10 = 0.40, or about 0.54 for 15 tests (assuming independence; correlated variables give somewhat less). This is plain arithmetic from the Wilks formula, and it is why "no correction" is hard to defend in a tool that highlights winners.
- Variables at one place are often strongly correlated (for example LST, air temperature and NDVI). BY 2001's PRDS result covers positive dependence, so BH remains valid for positively correlated tests. Negatively correlated pairs (for example snow cover vs temperature) technically fall outside PRDS, but with m around 10 the practical risk is small. If strict guarantees are needed, Holm is valid under any dependence.
- Practical recommendation: keep BH at q = 0.05 or 0.10 across the variable set. Show the raw p-value and the BH-adjusted q-value side by side, and label the result "passes the many-tests check." Offer Holm as a "strict mode." Do not apply alpha_FDR = 2 x alpha_global here: that rule is specific to strongly correlated gridded fields and to the goal of a field-level test.
- Do not pool the per-place variable family with the per-map pixel family. They answer different questions and should be corrected separately.

### Gaps
- I found no climate-specific primary source that compares BH vs Holm vs none for about 10 variables at a single site. The recommendation above is inference from general multiple-testing theory.

---

## 4. How IPCC AR6, NOAA NCEI, NASA GISS, Copernicus C3S and NCA5 report trends and significance

### Takeaway
IPCC uses a calibrated likelihood scale (virtually certain 99-100%, very likely 90-100%, likely 66-100%, and so on), plus a separate qualitative confidence scale, and gives 90% ("very likely") ranges in brackets. AR6 observed-trend maps mark *non*-significant grid boxes with "x" after an AR(1) serial-correlation adjustment, typically at the 10% level, and do not apply FDR. US agencies report linear trends per decade or per century, with significance usually stated as 95% confidence.

### Cited Findings
**IPCC calibrated language (AR5 guidance note, Mastrandrea et al. 2010, carried into AR6).** [V-full]
- Table 1, likelihood scale: virtually certain 99-100%; very likely 90-100%; likely 66-100%; about as likely as not 33-66%; unlikely 0-33%; very unlikely 0-10%; exceptionally unlikely 0-1%. Additional terms: extremely likely 95-100%, more likely than not >50-100%, extremely unlikely 0-5%. — [IPCC AR5 Uncertainty Guidance Note](https://www.ipcc.ch/site/assets/uploads/2018/05/uncertainty-guidance-note.pdf) (copy read: [Berkeley mirror](https://www.stat.berkeley.edu/users/aldous/157/Papers/ipcc_uncertainty-guidance-note.pdf))
- Confidence "should not be interpreted probabilistically, and it is distinct from 'statistical confidence'." Likelihood "can be used to express a probabilistic estimate of the occurrence of a single event or of an outcome (e.g., a climate parameter, observed trend, or projected change lying in a given range)." Authors should give probabilistic information (percentile ranges, distributions) "instead of likelihood when possible." — [IPCC guidance note](https://www.ipcc.ch/site/assets/uploads/2018/05/uncertainty-guidance-note.pdf)
- A 2022 critique notes the guidance remains somewhat unclear on how to combine evidence and agreement into confidence. — [Climatic Change 2022 (s10584-022-03382-3)](https://eprints.whiterose.ac.uk/190055/1/s10584-022-03382-3.pdf)

**IPCC AR6 WG1.** [V-abstract]
- The SPM uses the same scale ("virtually certain 99–100% probability, very likely 90–100%"...). Confidence levels (very low to very high) are in italics. Square brackets give the "very likely range, or 90% interval." Some key findings are plain statements of fact. Where lines of evidence conflict, the SPM assigns "low confidence" in the sign of a trend. — [AR6 WG1 SPM PDF](https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_SPM.pdf)
- Figure 2.11b (HadCRUTv5 trends 1900-1980 and 1981-2020): "Significance is assessed following AR(1) adjustment after Santer et al. (2008), '×' marks denote non-significant trends." — [AR6 Fig 2.11 page](https://www.ipcc.ch/report/ar6/wg1/figures/chapter-2/figure-2-11/) (from a search excerpt; ipcc.ch returned 403 to direct fetch)
- Cross-Chapter Box 3.1 Figure 1 and Chapter 8 maps: cross marks indicate trends "not significant at the 10% level," based on t-tests that take serial correlation into account. — [AR6 CCBox 3.1 Fig 1](https://www.ipcc.ch/report/ar6/wg1/figures/chapter-3/ccbox-3-1-figure-1/); [AR6 Chapter 8](https://www.ipcc.ch/report/ar6/wg1/chapter/chapter-8/) (search excerpts)
- For TS Cross-Section Box TS.1 Figure 1, the hatching in the lower map is described as marking "areas of conflicting model evidence on significance of changes," which is a model-agreement criterion, not FDR. — [AR6 TS CSB TS.1 Fig 1](https://www.ipcc.ch/report/ar6/wg1/figures/technical-summary/ts-ccbox-1-figure-1/) (search excerpt)
- AR6 projection maps (Cross-Chapter Box Atlas.1, "Approach C" in the SPM figures) use three markings. No overlay means "robust change" (at least 66% of models show a change above the internal-variability threshold and at least 80% agree on sign). Diagonal lines mean "no change or no robust change." Crossed lines mean "conflicting signals." [PK] — [AR6 Atlas chapter](https://www.ipcc.ch/report/ar6/wg1/chapter/atlas/)

**NOAA NCEI / Climate.gov.** [V-abstract]
- Climate.gov states linear trends as a rate per century (for example 1.45 °F per century for the contiguous US since 1895) and describes significance as 95% confidence that a trend is real (p <= 0.05). It warns that linear trends can be strongly influenced by start and end values, especially with few data points. — [Climate.gov comment/FAQ](https://www.climate.gov/comment/3162)
- EPA indicators built on Climate at a Glance (nClimDiv) compute trends by ordinary least-squares regression on climate-division anomalies. — [EPA seasonal temperature documentation](https://www.epa.gov/system/files/documents/2024-06/seasonal-temperature_documentation.pdf)

**NCA5 / USGCRP.** [V-abstract]
- NCA5 key messages "almost always include calibrated language" for confidence and likelihood. — [AMS 2024 abstract J12.3](https://ams.confex.com/ams/104ANNUAL/webprogram/Paper431711.html)
- USGCRP likelihood and confidence language derives from NCA3, IPCC AR5 and the Climate and Health assessment. Confidence and likelihood rest on author-team expert assessment, documented in "Traceable Accounts." — [CSSR (NCA4 Vol I) Guide to this Report](https://d3fwy0cye6m39j.cloudfront.net/chapter/front-matter-guide)

### Inferences
- Major bodies differ: IPCC marks non-significant cells; Wilks argues for FDR-controlled marking of significant cells. A student tool could follow the IPCC convention (hatch or fade "not distinguishable from zero") while choosing the threshold by BH-FDR. That would be more rigorous than AR6's per-cell 10% tests, and the tool should say so honestly.
- The IPCC likelihood words are good vocabulary for a student tool if the numbers are attached (see Q5). For example, if the 90% CI of a trend excludes zero, "very likely warming" is roughly defensible, but only as a statistical statement, not an IPCC-style expert assessment.

### Gaps
- NASA GISS (GISTEMP) and Copernicus C3S methods pages were not fetched this session. From prior knowledge [PK]: GISTEMP publishes a 95% confidence interval on annual global means (Lenssen et al. 2019, JGR), and C3S Global Climate Highlights report warming rates with ranges and dataset spread. Both need verification.
- NOAA's current Climate at a Glance page states trends per decade, but I did not verify its exact significance method; it appears to be OLS with no displayed significance.
- The exact AR6 thresholds for "robust change" in Atlas.1 are [PK], not verified.
- ipcc.ch blocked direct fetches (403), so the AR6 captions above come from search-engine excerpts.

---

## 5. How people interpret "significant," p-values, CIs and likelihood words; visual practices

### Takeaway
Laypeople across 24 countries read IPCC likelihood words as closer to 50% than intended. Adding numeric ranges next to the words ("very likely (90-100%)") reduces, but does not eliminate, that misreading. This argues strongly for always pairing words with numbers and graphics.

### Cited Findings
- Budescu, Por, Broomell & Smithson 2014, Nature Climate Change 4:508-512: 25 samples in 24 countries and 17 languages. Laypeople interpret IPCC statements as conveying probabilities closer to 50% than intended. The effect is "exaggerated for negatively worded phrases." — [ANU research portal](https://researchportalplus.anu.edu.au/en/publications/the-interpretation-of-ipcc-probabilistic-statements-around-the-wo/); [ANU ICEDS story](https://iceds.anu.edu.au/research/stories/does-language-impact-climate-scepticism) [V-abstract]
- The dual-format fix (words plus numeric ranges in the sentence) "didn't cure the problem but it did help." A CMU release says supplementing words with numeric values clarifies uncertainty for most respondents. — [ANU ICEDS](https://iceds.anu.edu.au/research/stories/does-language-impact-climate-scepticism); [CMU news 2014](https://www.cmu.edu/news/stories/archives/2014/april/april30_climatebroomell.html) [V-abstract]
- Budescu's 2016 IPCC expert-meeting slides summarize that the public reads IPCC statements as less certain than intended, and point to an evidence-based lexicon. — [Budescu, IPCC Oslo 2016](https://www.ipcc.ch/site/assets/uploads/2016/02/Budescu_IPCC_Communication_Meeting_OSLO_February_2016.pdf) [V-abstract]
- Budescu, Broomell & Por 2009, Psychological Science 20:299-308, "Improving communication of uncertainty in the reports of the IPCC": the dual verbal-numeric format improved alignment with IPCC intent. [PK] — [doi:10.1111/j.1467-9280.2009.02284.x](https://doi.org/10.1111/j.1467-9280.2009.02284.x)
- Budescu et al. 2012 (Climatic Change 113:181-200), "Effective communication of uncertainty in the IPCC reports," extended this work. [PK] — [doi:10.1007/s10584-011-0330-3](https://doi.org/10.1007/s10584-011-0330-3)
- Wilks notes p-value misinterpretation even among scientists: it is "quite incorrect to interpret a p-value as the probability that the null hypothesis is true." — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)

### Inferences
- Visual practices (inference, consistent with the sources above): show the trend line with a shaded 95% confidence band. Show the trend estimate as a number with a +/- range ("+0.21 °C/decade, likely range 0.15 to 0.27"). Add a plain verbal label paired with a number ("very likely increasing: 90%+"). On maps, fade or hatch cells that fail BH instead of only stippling the winners.
- "Check back in N years" messaging is a reasonable student-facing framing for "not yet detectable." Time-of-emergence and detection-time concepts support it (for example, Weatherhead et al. 1998, JGR, gives the years needed to detect a trend given noise and autocorrelation [PK]), but I did not verify any source that tests this messaging with students.
- Avoid "significant at the 95% level" (Wilks flags this as non-standard), and avoid "proven"/"no trend" dichotomies.

### Gaps
- I found no study testing confidence bands, uncertainty meters or "check back in N years" specifically with high school or college students in a climate-data tool.
- Full texts of the Budescu papers were not read; the findings come from the abstract and institutional summaries.

---

## 6. ASA 2016 statement and the 2019 "world beyond p < 0.05" editorial: implications for phrasing

### Takeaway
The ASA (2016) says p-values do not measure the probability that a hypothesis is true or the size of an effect, and that conclusions should not rest only on crossing p < 0.05. The 2019 editorial goes further and says "don't say 'statistically significant'." A student tool should lead with effect size and uncertainty ranges, report p-values continuously, and use "significant" sparingly, if at all, as a defined label.

### Cited Findings
- Wasserstein & Lazar 2016, "The ASA Statement on p-Values: Context, Process, and Purpose," The American Statistician 70(2):129-133. It states six principles: (1) p-values can indicate how incompatible the data are with a specified statistical model; (2) p-values do not measure the probability that the hypothesis is true, or the probability that the data were produced by chance alone; (3) scientific conclusions and decisions should not be based only on whether a p-value passes a threshold; (4) proper inference requires full reporting and transparency; (5) a p-value or statistical significance does not measure the size of an effect or the importance of a result; (6) by itself, a p-value does not provide a good measure of evidence about a model or hypothesis. [PK; publisher returned 403] — [doi:10.1080/00031305.2016.1154108](https://doi.org/10.1080/00031305.2016.1154108)
- Wasserstein, Schirm & Lazar 2019, "Moving to a World Beyond 'p < 0.05'," The American Statistician 73(sup1):1-19. It recommends: "Don't base your conclusions solely on whether an association or effect was found to be 'statistically significant'"; "Don't believe that an association or effect exists just because it was statistically significant"; "Don't believe that an association or effect is absent just because it was not statistically significant"; and "don't say 'statistically significant'." It also offers the "ATOM" mnemonic: Accept uncertainty; be Thoughtful, Open, and Modest. [PK; publisher returned 403] — [doi:10.1080/00031305.2019.1583913](https://doi.org/10.1080/00031305.2019.1583913)
- Wilks (2016) itself calls alpha = 0.05 "the most common, although an arbitrary, choice." — [Wilks 2016 manuscript](https://ams.confex.com/ams/96Annual/webprogram/Manuscript/Paper276937/FDRpaper2cols.pdf)

### Inferences (suggested phrasing for the tool)
- Lead with magnitude and range: "Surface temperature here rose about 0.3 °C per decade (95% range 0.1 to 0.5)."
- Then give the evidence strength in words plus numbers: "That's strong evidence of a real upward trend (p = 0.004; it still holds after checking all 12 variables together)."
- When a result fails: "Not enough evidence yet to tell this trend apart from natural ups and downs. This does NOT mean there's no change. With this much year-to-year noise, you'd need about N more years of data to know." Principle 6 and the 2019 "don't believe absent" point support this framing.
- Never say "proves," "no trend," or "95% chance the trend is real" (a p-value or CI is not that probability; see ASA principle 2).
- If the tool keeps a binary badge for UI reasons, call it something like "passes the many-tests check (FDR 5%)" and link to a one-paragraph explainer, rather than using an unexplained "significant."

### Gaps
- I could not fetch the ASA 2016 or 2019 texts this session (403 from tandfonline). The principles and quotes above are from prior knowledge and are widely reproduced, but the report writer should verify the exact wording before quoting.
