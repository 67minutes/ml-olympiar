"""ML-1: element thresholds from Gaussian mixtures on log10 values (AGENTS.md §6 task 1).

The objective analogue of Sinclair probability-plot partitioning: populations are GMM
components, thresholds are where adjacent populations' weighted densities cross. Lab
values are reported in steps (1, 2, 3 ppm...), which a GMM would fit as populations, so
values are dequantised (jittered within their reporting step) before fitting. All work is
on log10 values; thresholds are returned in log10 unless stated.
"""
import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

REG_COVAR = 0.05 ** 2   # log10 variance floor: no component narrower than ~12% (linear)
MIN_COMP_N = 5          # every component must hold at least this many samples (n·w)
KMAX = 5


def step(v: np.ndarray) -> np.ndarray:
    """Reporting step of each value (10^-k for the fewest decimals k that fit), capped at
    0.5·value so a dequantised value stays positive (≥ 0.75·value)."""
    v = np.asarray(v, dtype=float)
    r = np.full(v.shape, 1e-7)
    todo = np.ones(v.shape, bool)
    for k in range(7):
        x = v * 10 ** k
        hit = todo & np.isclose(x, np.round(x), rtol=0, atol=1e-6)
        r[hit] = 10.0 ** -k
        todo &= ~hit
    return np.minimum(r, 0.5 * v)


def dequantise(v: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """log10 of each value jittered uniformly within ±step/2."""
    v = np.asarray(v, dtype=float)
    r = step(v)
    return np.log10(v + rng.uniform(-r / 2, r / 2))


def fit_gmm(x: np.ndarray, k: int, n_init: int = 10, seed: int = 0) -> GaussianMixture:
    return GaussianMixture(k, n_init=n_init, random_state=seed,
                           reg_covar=REG_COVAR).fit(np.asarray(x).reshape(-1, 1))


def components(g: GaussianMixture) -> pd.DataFrame:
    """Component mean, SD and weight (log10), sorted by mean (population 1 = lowest)."""
    c = pd.DataFrame({"mean": g.means_.ravel(), "sd": np.sqrt(g.covariances_.ravel()),
                      "weight": g.weights_})
    return c.sort_values("mean").reset_index(drop=True)


def admissible(g: GaussianMixture, n: int) -> bool:
    return bool((g.weights_ * n >= MIN_COMP_N).all())


def bic_curve(x: np.ndarray, kmax: int = KMAX, n_init: int = 5, seed: int = 0) -> pd.Series:
    """BIC per K on one sample; inadmissible models get +inf."""
    out = {}
    for k in range(1, kmax + 1):
        g = fit_gmm(x, k, n_init, seed)
        out[k] = g.bic(np.asarray(x).reshape(-1, 1)) if admissible(g, len(x)) else np.inf
    return pd.Series(out)


def select_k(v: np.ndarray, kmax: int = KMAX, n_draws: int = 20, seed: int = 0,
             n_init: int = 5) -> tuple[int, pd.Series]:
    """K minimising the BIC averaged over `n_draws` dequantisations. Returns (K, mean BIC)."""
    curves = [bic_curve(dequantise(v, np.random.default_rng(seed + d)), kmax, n_init, seed)
              for d in range(n_draws)]
    bic = pd.concat(curves, axis=1).mean(axis=1)
    return int(bic.idxmin()), bic


def crossing(m1, s1, w1, m2, s2, w2) -> float:
    """x in (m1, m2) where w1·N(x; m1, s1) = w2·N(x; m2, s2); NaN if none (nested pair)."""
    a = 1 / (2 * s2 ** 2) - 1 / (2 * s1 ** 2)
    b = m1 / s1 ** 2 - m2 / s2 ** 2
    c = m2 ** 2 / (2 * s2 ** 2) - m1 ** 2 / (2 * s1 ** 2) + np.log(w1 * s2 / (w2 * s1))
    roots = [-c / b] if abs(a) < 1e-12 else np.roots([a, b, c])
    inside = sorted(r.real for r in np.atleast_1d(roots) if abs(np.imag(r)) < 1e-12 and m1 < r.real < m2)
    return inside[0] if inside else np.nan


def crossings(comp: pd.DataFrame) -> list[float]:
    """Threshold between each pair of adjacent populations (log10); NaN = not resolved."""
    return [crossing(*comp.loc[i, ["mean", "sd", "weight"]], *comp.loc[i + 1, ["mean", "sd", "weight"]])
            for i in range(len(comp) - 1)]


def ashman_d(m1, s1, m2, s2) -> float:
    """Ashman's D: separation of two Gaussians; D > 2 means a clean bimodal split."""
    return float(np.sqrt(2) * abs(m2 - m1) / np.sqrt(s1 ** 2 + s2 ** 2))


def fallback(comp: pd.DataFrame) -> float:
    """No population break: mean + 2·SD of the fitted (mixture) log-distribution."""
    mu = (comp.weight * comp["mean"]).sum()
    var = (comp.weight * (comp.sd ** 2 + (comp["mean"] - mu) ** 2)).sum()
    return float(mu + 2 * np.sqrt(var))


def robust_thresholds(v) -> tuple[float, float]:
    """Median + 2·MAD and Tukey upper fence (Q3 + 1.5·IQR), on log10, back-transformed."""
    lx = np.log10(pd.Series(v).dropna().to_numpy())
    med = np.median(lx)
    mad = 1.4826 * np.median(np.abs(lx - med))
    q1, q3 = np.percentile(lx, [25, 75])
    return float(10 ** (med + 2 * mad)), float(10 ** (q3 + 1.5 * (q3 - q1)))


def classify(g: GaussianMixture, t_log: list[float], v: pd.Series,
             cens: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Population index (1 + number of thresholds at or below the value; censored -> 1;
    NaN where not analysed) and the posterior of the top component (NaN when K = 1)."""
    ok = v.notna()
    lx = np.log10(v[ok].to_numpy())
    t = np.sort(np.asarray([x for x in t_log if np.isfinite(x)]))
    pop = pd.Series(np.nan, index=v.index)
    pop[ok] = 1 + np.searchsorted(t, lx, side="right")
    pop[ok & cens.fillna(False).astype(bool)] = 1
    p_top = pd.Series(np.nan, index=v.index)
    if g.n_components > 1:
        p_top[ok] = g.predict_proba(lx.reshape(-1, 1))[:, int(np.argmax(g.means_.ravel()))]
    return pop.astype("Int64"), p_top


def bootstrap(v: np.ndarray, k: int, kmax: int = KMAX, n_boot: int = 200, seed: int = 0,
              n_init: int = 3) -> tuple[dict, np.ndarray]:
    """Resample + new dequantisation per draw. Returns (frequency of each re-selected K,
    thresholds at fixed K: n_boot × (K−1), or n_boot × 1 fallback values when K = 1)."""
    v = np.asarray(v, dtype=float)
    rng = np.random.default_rng(seed)
    ks, ts = [], []
    for _ in range(n_boot):
        x = dequantise(v[rng.integers(0, len(v), len(v))], rng)
        ks.append(int(bic_curve(x, kmax, n_init, seed).idxmin()))
        comp = components(fit_gmm(x, k, n_init, seed))
        ts.append(crossings(comp) if k > 1 else [fallback(comp)])
    freq = pd.Series(ks).value_counts(normalize=True).sort_index()
    return {int(i): float(f) for i, f in freq.items()}, np.array(ts, dtype=float)


def confidence(k_freq: float, min_d: float, n_distinct: int, pct_cens: float) -> str:
    """Heuristic label (stated in the report): how far to trust an element's thresholds."""
    if not 0 <= k_freq <= 1:
        raise ValueError(f"k_freq must be a share, got {k_freq}")
    if k_freq < 0.5 or n_distinct < 20 or pct_cens > 30:
        return "low"
    sep_ok = np.isnan(min_d) or min_d >= 2
    if k_freq >= 0.7 and sep_ok and n_distinct >= 30 and pct_cens <= 25:
        return "high"
    return "medium"
