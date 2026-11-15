"""Checks for earthpull.trends (the method in reports/Trend analysis methods for Earth data.md)."""
import numpy as np
import pandas as pd
import pytest

from earthpull.trends import _ols_ar1, analyze, ols_ar1_map, trend_report

IDX = pd.date_range("2003-01-01", periods=264, freq="MS")  # 22 years of months
TY = (IDX.year + (IDX.month - 0.5) / 12).to_numpy(float)


def ar1(n, phi, rng, sd=1.0):
    e = rng.normal(0, sd, n)
    x = np.empty(n)
    x[0] = e[0] / np.sqrt(1 - phi ** 2)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


def seasonal():
    return 5 * np.sin(2 * np.pi * (IDX.month - 1) / 12)


@pytest.mark.parametrize("phi", [0.3, 0.6, 0.85])
def test_false_positive_rate_near_nominal(phi):
    rng = np.random.default_rng(1)
    reps, rej, clear = 200, 0, 0
    for _ in range(reps):
        s = pd.Series(seasonal() + ar1(len(IDX), phi, rng), index=IDX)
        r = trend_report(s)
        rej += r["p_ar1"] < 0.05
        clear += (r["p_ar1"] < 0.05) and (r["sen_ci_low"] > 0 or r["sen_ci_high"] < 0)
    assert rej / reps <= 0.10, f"AR(1)-adjusted test rejected {rej / reps:.0%} of trendless series"
    assert clear / reps <= 0.08


def test_detects_real_trend_and_estimates_it():
    rng = np.random.default_rng(2)
    slopes, hits = [], 0
    for _ in range(100):
        y = seasonal() + 0.08 * (TY - TY[0]) + ar1(len(IDX), 0.5, rng, 0.6)  # 0.8 per decade
        r = trend_report(pd.Series(y, index=IDX))
        slopes.append(r["slope_per_decade"])
        hits += r["p_ar1"] < 0.05
    assert abs(np.mean(slopes) - 0.8) < 0.05
    assert hits >= 90


def test_matches_statsmodels_glsar():
    import statsmodels.api as sm
    from earthpull.trends import _design

    rng = np.random.default_rng(3)
    y = seasonal() + 0.05 * (TY - TY[0]) + ar1(len(IDX), 0.6, rng)
    ok = np.ones(len(y), bool)
    ours = _ols_ar1(TY, y, ok)
    g = sm.GLSAR(y, _design(TY), rho=1).iterative_fit(maxiter=10)
    assert abs(ours["slope"] - g.params[1]) < 0.3 * abs(g.params[1])
    assert (ours["p"] < 0.05) == (g.pvalues[1] < 0.05)


def test_gaps_are_not_interpolated_and_still_work():
    rng = np.random.default_rng(4)
    y = seasonal() + 0.05 * (TY - TY[0]) + ar1(len(IDX), 0.5, rng)
    s = pd.Series(y, index=IDX)
    s.loc["2017-07-01":"2018-05-01"] = np.nan  # GRACE-like mission gap
    s = s.drop(s.sample(15, random_state=0).index)  # scattered missing months, rows absent
    r = trend_report(s)
    assert r["months"] < 264 and np.isfinite(r["slope_per_decade"]) and np.isfinite(r["p_ar1"])
    assert abs(r["slope_per_decade"] - 0.5) < 0.35


def test_map_matches_single_series():
    rng = np.random.default_rng(5)
    Y = np.column_stack([seasonal() + 0.03 * k * (TY - TY[0]) + ar1(len(IDX), 0.4, rng) for k in range(5)])
    sl, pv, _ = ols_ar1_map(Y, TY)
    for k in range(5):
        one = _ols_ar1(TY, Y[:, k], np.ones(len(IDX), bool))
        assert np.isclose(sl[k], 10 * one["slope"]) and np.isclose(pv[k], one["p"], rtol=1e-6, atol=1e-12)


def test_known_step_is_not_reported_as_trend():
    rng = np.random.default_rng(6)
    y = seasonal() + 3.0 * (TY >= 2018.42) + ar1(len(IDX), 0.3, rng, 0.5)  # instrument jump, no trend
    s = pd.Series(y, index=IDX)
    no_step, with_step = trend_report(s), trend_report(s, breaks=(2018.42,))
    assert no_step["p_ar1"] < 0.05  # a jump looks like a trend if ignored
    assert with_step["p_ar1"] > 0.05 and with_step["robust_to_breaks"] is False


def test_verdicts_and_short_records():
    rng = np.random.default_rng(7)
    wide = pd.DataFrame({
        "rising": seasonal() + 0.1 * (TY - TY[0]) + ar1(len(IDX), 0.5, rng, 0.5),
        "noise": seasonal() + ar1(len(IDX), 0.5, rng),
    }, index=IDX.to_period("M"))
    wide.loc[wide.index[:200], "short"] = np.nan
    wide["short"] = wide["short"].astype(float)
    res = analyze(wide).set_index("id")
    assert res.loc["rising", "verdict"] == "Clear rise"
    assert res.loc["short", "verdict"] == "Too short to tell"


def test_clear_verdict_rate_on_trendless_series():
    hits = 0
    for k in range(150):
        g = np.random.default_rng(1000 + k)
        w = pd.DataFrame({"a": seasonal() + ar1(len(IDX), 0.5, g), "b": seasonal() + ar1(len(IDX), 0.5, g)},
                         index=IDX.to_period("M"))
        hits += analyze(w).verdict.str.startswith("Clear").sum()
    assert hits / 300 <= 0.06, f"'Clear' on {hits / 300:.1%} of trendless series"


def test_season_trend_finds_summer_only_change():
    from earthpull.trends import season_trend
    rng = np.random.default_rng(8)
    y = np.asarray(seasonal(), float) + rng.normal(0, 0.3, len(IDX))
    summer = np.isin(IDX.month, [6, 7, 8])
    y[summer] += 0.08 * (TY[summer] - TY[0])  # rising in summer only
    s = pd.Series(y, index=IDX)
    jja, djf = season_trend(s, (6, 7, 8)), season_trend(s, (12, 1, 2))
    assert jja["verdict"] == "Clear rise" and abs(jja["slope_per_decade"] - 0.8) < 0.2
    assert not djf["verdict"].startswith("Clear")
    assert djf["years"] == 21  # Dec 2024 has no Jan/Feb 2025, and 2003 lacks Dec 2002


def test_percent_change_and_buffer():
    from shapely.geometry import box as sbox

    from earthpull.trends import buffer_km, percent_change, region_area_km2
    y = 10.0 * (1 + 0.5 * (TY - TY[0]) / (TY[-1] - TY[0]))  # rises from 10 to 15: +50% over the record
    assert abs(percent_change(pd.Series(y, index=IDX)) - 50) < 1
    sq = sbox(-1, -1, 1, 1)  # about 222 km x 222 km at the equator
    assert 48000 < region_area_km2(sq) < 50500
    grown = buffer_km(sq, 100)
    assert region_area_km2(grown) > region_area_km2(sq) * 2
