import numpy as np
import pandas as pd
import pytest

from src import thresholds as th


def lognormal(rng, mu, sd, n):
    return 10 ** rng.normal(mu, sd, n)


def test_step_and_dequantise():
    v = np.array([2.0, 0.05, 0.125, 150.0])
    assert np.allclose(th.step(v), [1.0, 0.01, 0.001, 1.0])
    assert np.allclose(th.step(np.array([0.5])), [0.1])        # capped at 0.5·v only if smaller
    assert np.allclose(th.step(np.array([1.0])), [0.5])        # 1 ppm: step 1 capped to 0.5
    x = th.dequantise(np.array([2.0] * 1000), np.random.default_rng(0))
    lin = 10 ** x
    assert lin.min() >= 1.5 and lin.max() <= 2.5 and lin.std() > 0.2


def test_two_populations_found_and_threshold_between():
    rng = np.random.default_rng(1)
    v = np.concatenate([lognormal(rng, -1.0, 0.2, 400), lognormal(rng, 0.5, 0.2, 200)])
    k, bic = th.select_k(v, kmax=4, n_draws=3)
    assert k == 2 and bic.idxmin() == 2
    comp = th.components(th.fit_gmm(th.dequantise(v, np.random.default_rng(0)), k))
    t = th.crossings(comp)
    assert len(t) == 1 and -1.0 < t[0] < 0.5
    assert th.ashman_d(*comp.loc[0, ["mean", "sd"]], *comp.loc[1, ["mean", "sd"]]) > 2


def test_single_population_gives_k1_and_fallback():
    rng = np.random.default_rng(2)
    v = lognormal(rng, 0.0, 0.3, 500)
    k, _ = th.select_k(v, kmax=4, n_draws=3)
    assert k == 1
    comp = th.components(th.fit_gmm(np.log10(v), 1))
    assert np.isclose(th.fallback(comp), comp["mean"].iloc[0] + 2 * comp["sd"].iloc[0])


def test_dequantising_removes_reporting_steps():
    rng = np.random.default_rng(3)
    v = np.round(lognormal(rng, 0.6, 0.25, 600))               # integer ppm, like drillhole Ag
    v = v[v > 0]
    raw_bic = [th.fit_gmm(np.log10(v), k).bic(np.log10(v).reshape(-1, 1)) for k in (1, 2, 3)]
    assert np.argmin(raw_bic) > 0                              # the raw fit chases the steps
    k, _ = th.select_k(v, kmax=4, n_draws=5)
    assert k == 1


def test_admissible_rejects_tiny_component():
    rng = np.random.default_rng(4)
    x = np.log10(np.concatenate([lognormal(rng, 0.0, 0.2, 300), [1e3, 1.01e3, 0.99e3]]))
    g = th.fit_gmm(x, 2)
    assert th.components(g)["weight"].min() * len(x) < 5
    assert not th.admissible(g, len(x))
    assert th.admissible(th.fit_gmm(x, 1), len(x))


def test_crossing_none_when_nested():
    # a narrow component sitting inside a broad one: no crossing between the means
    comp = pd.DataFrame({"mean": [1.90, 2.02], "sd": [0.26, 0.52], "weight": [0.6, 0.4]})
    assert np.isnan(th.crossings(comp)[0])


def test_robust_thresholds():
    v = 10 ** np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    mad, tukey = th.robust_thresholds(v)
    # log10: median 2, MAD 1·1.4826; Q1 1, Q3 3, IQR 2
    assert np.isclose(mad, 10 ** (2 + 2 * 1.4826))
    assert np.isclose(tukey, 10 ** (3 + 1.5 * 2))


def test_classify():
    rng = np.random.default_rng(5)
    x = np.concatenate([rng.normal(-1, 0.2, 200), rng.normal(0.5, 0.2, 200)])
    g = th.fit_gmm(x, 2)
    v = pd.Series([0.01, 5.0, np.nan, 0.02])
    cens = pd.Series([False, False, False, True])
    pop, p = th.classify(g, [-0.25], v, cens)
    assert pop.tolist()[:2] == [1, 2] and pd.isna(pop.iloc[2]) and pop.iloc[3] == 1
    assert p.dropna().between(0, 1).all() and p.iloc[1] > 0.9 and p.iloc[0] < 0.1


def test_bootstrap_shapes():
    rng = np.random.default_rng(6)
    v = np.concatenate([lognormal(rng, -1.0, 0.2, 300), lognormal(rng, 0.5, 0.2, 150)])
    kfreq, t = th.bootstrap(v, k=2, kmax=3, n_boot=10, seed=0)
    assert t.shape == (10, 1) and abs(sum(kfreq.values()) - 1) < 1e-9
    assert kfreq.get(2, 0) >= 0.7
    assert -1.0 < np.nanmedian(t[:, 0]) < 0.5


def test_confidence():
    assert th.confidence(k_freq=0.9, min_d=2.5, n_distinct=100, pct_cens=5) == "high"
    assert th.confidence(k_freq=0.4, min_d=2.5, n_distinct=100, pct_cens=5) == "low"
    assert th.confidence(k_freq=0.9, min_d=2.5, n_distinct=15, pct_cens=5) == "low"
    assert th.confidence(k_freq=0.9, min_d=1.5, n_distinct=100, pct_cens=5) == "medium"
    with pytest.raises(ValueError):
        th.confidence(k_freq=1.5, min_d=2, n_distinct=10, pct_cens=0)
