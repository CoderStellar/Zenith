"""Checks for earthpull.engine (correlation engine)."""
import numpy as np
import pandas as pd

from earthpull import engine

IDX = pd.period_range("2003-01", periods=264, freq="M")
T = np.arange(264) / 120.0  # decades


def ar1(n, phi, rng, sd=1.0):
    e = rng.normal(0, sd, n)
    x = np.empty(n)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


def season(amp=3.0, phase=0.0):
    return amp * np.sin(2 * np.pi * (np.arange(264) % 12) / 12 + phase)


def test_shared_trend_alone_is_not_a_link():
    rng = np.random.default_rng(0)
    w = pd.DataFrame({"precip": season() + 2.0 * T + ar1(264, 0.4, rng),   # both drift up, otherwise unrelated
                      "soil_moisture": season(phase=1) + 2.0 * T + ar1(264, 0.4, rng)}, index=IDX)
    res = engine.run(w, max_lag=2, n_surrogates=200)
    assert res["pairs"].iloc[0]["level"] == 0, res["pairs"].iloc[0]["verdict"]
    pt = res["partial_trends"].set_index(["y", "x"])
    # X adds nothing beyond the shared drift, so Y's trend must NOT be credited to X
    assert not pt.loc[("soil_moisture", "precip"), "verdict"].startswith("Trend no longer clear")


def test_real_driver_is_found_and_explains_the_trend():
    rng = np.random.default_rng(1)
    rain = season() + 1.5 * T + ar1(264, 0.3, rng)
    soil = 0.8 * (rain - season()) + season(phase=0.5) + 0.3 * ar1(264, 0.3, rng)  # soil follows rain
    res = engine.run(pd.DataFrame({"precip": rain, "soil_moisture": soil}, index=IDX), max_lag=2, n_surrogates=200)
    top = res["pairs"].iloc[0]
    assert top["level"] == 4 and top["r"] > 0.5, top["verdict"]
    pt = res["partial_trends"].set_index(["y", "x"])
    row = pt.loc[("soil_moisture", "precip")]
    assert row["p_alone"] < 0.05 and row["x_effect_p"] < 0.05
    assert row["verdict"].startswith("Trend no longer clear") and row["share_of_trend_x_accounts_for"] > 0.7


def test_compare_regions_reports_sign_flip():
    rng = np.random.default_rng(2)
    def place(sign):
        t = ar1(264, 0.3, rng)
        return pd.DataFrame({"air_temp": season() + t, "evaporation": season() + sign * 0.8 * t + 0.4 * ar1(264, 0.3, rng)},
                            index=IDX)
    tab, summary = engine.compare_regions({"wet place": place(+1), "dry place": place(-1)}, "air_temp", "evaporation", 2)
    assert set(tab.verdict) == {"Linked, same direction as the physics rule", "Linked, opposite to the physics rule"}
    assert "flips" in summary


def test_gaps_handled():
    rng = np.random.default_rng(3)
    w = pd.DataFrame({"precip": season() + ar1(264, 0.3, rng)}, index=IDX)
    w["water_storage"] = 0.7 * (w["precip"] - season()) + ar1(264, 0.3, rng) * 0.5
    w = w.drop(w.index[170:181])  # GRACE-style gap: rows missing entirely
    res = engine.run(w, max_lag=2, n_surrogates=100, breaks={"water_storage": (2018.42,)})
    assert len(res["pairs"]) == 1 and res["pairs"].iloc[0]["r"] > 0.4


def test_huge_valued_variable_does_not_break_trend_check():
    rng = np.random.default_rng(4)
    no2 = 4e15 + 1e15 * (season() / 3 - 0.4 * T + 0.3 * ar1(264, 0.4, rng))  # molecules/cm2 scale
    temp = season() + 0.7 * T + ar1(264, 0.3, rng)
    res = engine.run(pd.DataFrame({"no2": no2, "air_temp": temp}, index=IDX), max_lag=1, n_surrogates=100)
    row = res["partial_trends"].set_index(["y", "x"]).loc[("air_temp", "no2")]
    assert abs(row["trend_with_x_per_decade"]) > 0.3  # not numerically zeroed
