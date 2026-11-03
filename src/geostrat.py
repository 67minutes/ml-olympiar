"""ML-4: downhole geochem-stratigraphy with a Gaussian hidden Markov model (AGENTS.md §6 task 4).

One HMM is fitted across all holes on 1 m composites, so a state means the same chemistry in
every hole. A state is a chemical unit: a Gaussian emission (multi-element mean and
covariance in robust-scaled log10 units) plus a probability of staying in it from one metre
to the next. Sequences are contiguous runs of usable composites; a gap starts a new one.
States are numbered by mean log Au (state 1 = lowest). Uncertainty comes from the posterior
(forward-backward), the lab's reporting steps and censoring (draws), and sampling (pad
bootstrap refits aligned to the main model).

Azimuths are degrees clockwise from north.
"""
import logging

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree
from sklearn.mixture import GaussianMixture

from src import thresholds as th

logging.getLogger("hmmlearn").setLevel(logging.ERROR)

CENS_LOW = np.log10(3.0)   # censored values spread over [DL/3, DL] in log10
N_ITER = 500
TOL = 1e-4


# --- features -----------------------------------------------------------------------
def log_features(V: np.ndarray, cens: np.ndarray, dl: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """log10 of each column: censored cells uniform on [log DL − log 3, log DL], the others
    dequantised within their reporting step (ML-1)."""
    V = np.asarray(V, float)
    L = np.column_stack([th.dequantise(V[:, j], rng) for j in range(V.shape[1])])
    lo = np.log10(dl) - CENS_LOW
    U = lo + rng.uniform(0, 1, V.shape) * CENS_LOW
    return np.where(np.asarray(cens, bool), U, L)


def segments(site: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """Segment id per row (−1 where not ok). Rows must be in downhole order per hole; a new
    segment starts at each hole and after each not-ok row."""
    site, ok = np.asarray(site), np.asarray(ok, bool)
    new = np.r_[True, site[1:] != site[:-1]] | np.r_[True, ~ok[:-1]]
    seg = np.cumsum(new & ok) - 1
    return np.where(ok, seg, -1)


def lengths(seg: np.ndarray) -> np.ndarray:
    """Sequence lengths for hmmlearn, in row order of the ok rows (seg ≥ 0)."""
    s = seg[seg >= 0]
    _, idx, n = np.unique(s, return_index=True, return_counts=True)
    return n[np.argsort(idx)]


# --- models -------------------------------------------------------------------------
def fit_hmm(X: np.ndarray, lens: np.ndarray, k: int, min_covar: float, restarts: int = 10,
            seed: int = 0) -> GaussianHMM:
    """Best-of-`restarts` full-covariance Gaussian HMM (seeds seed..seed+restarts−1)."""
    best, best_ll = None, -np.inf
    for r in range(restarts):
        m = GaussianHMM(k, covariance_type="full", min_covar=min_covar, n_iter=N_ITER, tol=TOL,
                        random_state=seed + r)
        try:
            m.fit(X, lens)
            ll = m.score(X, lens)
        except (ValueError, np.linalg.LinAlgError):
            continue
        if np.isfinite(ll) and ll > best_ll:
            best, best_ll = m, ll
    if best is None:
        raise RuntimeError(f"no HMM restart converged for K={k}")
    return best


def fit_gmm(X: np.ndarray, k: int, min_covar: float, restarts: int = 10, seed: int = 0) -> GaussianMixture:
    """The comparator: the same emissions without transitions."""
    return GaussianMixture(k, covariance_type="full", reg_covar=min_covar, n_init=restarts,
                           random_state=seed, max_iter=N_ITER, tol=TOL).fit(X)


def order(means: np.ndarray, col: int = 0) -> np.ndarray:
    """Internal state indices sorted by the mean of column `col` (state 1 = lowest)."""
    return np.argsort(means[:, col], kind="stable")


def align(ref_means: np.ndarray, means: np.ndarray) -> np.ndarray:
    """perm such that means[perm[i]] is the state matched to ref state i (Hungarian, Euclidean)."""
    cost = np.linalg.norm(ref_means[:, None, :] - means[None, :, :], axis=2)
    r, c = linear_sum_assignment(cost)
    return c[np.argsort(r)]


def occupancy(P: np.ndarray, site: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per state: expected count (Σ posterior) and number of holes where it is the argmax."""
    lab = P.argmax(1)
    holes = np.array([len(np.unique(site[lab == j])) for j in range(P.shape[1])])
    return P.sum(0), holes


def run_length(transmat: np.ndarray) -> np.ndarray:
    """Expected stay in each state, in composites (1 m): 1 / (1 − a_kk)."""
    d = np.clip(np.diag(transmat), 0, 1 - 1e-12)
    return 1.0 / (1.0 - d)


# --- sequences ----------------------------------------------------------------------
def switch_rate(labels, seg) -> float:
    """Label changes per 100 adjacent pairs within segments (≈ per 100 m on 1 m composites);
    pairs with a missing label are skipped."""
    lab, seg = pd.Series(labels).to_numpy(object), np.asarray(seg)
    same = (seg[1:] == seg[:-1]) & (seg[1:] >= 0)
    known = pd.notna(lab[1:]) & pd.notna(lab[:-1])
    pair = same & known
    if not pair.any():
        return np.nan
    return 100.0 * float((lab[1:][pair] != lab[:-1][pair]).sum()) / float(pair.sum())


def collapse_repeats(V: np.ndarray, seg: np.ndarray, shared: np.ndarray) -> np.ndarray:
    """Keep-mask that drops a composite repeating the previous one in its segment (flagged
    `comp_shared_src` and identical values): one observation per long source sample."""
    V, seg, shared = np.asarray(V, float), np.asarray(seg), np.asarray(shared, bool)
    rep = np.r_[False, (seg[1:] == seg[:-1]) & np.all(V[1:] == V[:-1], axis=1) & shared[1:]]
    return ~rep


# --- display ------------------------------------------------------------------------
STATE_PALETTE = {5: ["#2b4c9b", "#3d9fd0", "#8f6bb8", "#e88a2e", "#a51c30"]}   # validated (dataviz checks)


def state_colours(k: int) -> list[str]:
    """Hex colours for states ordered by Au (low Au blue → high Au red). K = 5 uses a palette
    checked for lightness, chroma and normal-vision separation; adjacent colour-blind ΔE is
    6.8, so state numbers are also written on long runs."""
    if k in STATE_PALETTE:
        return STATE_PALETTE[k]
    import matplotlib
    cmap = matplotlib.colormaps["RdYlBu_r"]
    return [matplotlib.colors.to_hex(cmap(x)) for x in np.linspace(0.05, 0.95, k)]


def run_label_rows(state: np.ndarray, seg: np.ndarray, min_len: int) -> np.ndarray:
    """Mask marking the middle composite of every run of one state ≥ `min_len` composites."""
    state, seg = np.asarray(state), np.asarray(seg)
    new = np.r_[True, (state[1:] != state[:-1]) | (seg[1:] != seg[:-1])]
    run = np.cumsum(new)
    out = np.zeros(len(state), bool)
    for r in np.unique(run):
        idx = np.flatnonzero(run == r)
        if len(idx) >= min_len:
            out[idx[len(idx) // 2]] = True
    return out


# --- spatial ------------------------------------------------------------------------
def pair_agreement(xyz: np.ndarray, labels: np.ndarray, hole: np.ndarray, edges) -> pd.DataFrame:
    """Share of composite pairs from different holes with the same label, by 3D distance bin,
    with the chance level Σ p_k² of the labels used."""
    xyz, labels, hole = np.asarray(xyz, float), np.asarray(labels), np.asarray(hole)
    edges = np.asarray(edges, float)
    pairs = cKDTree(xyz).query_pairs(edges[-1], output_type="ndarray")
    pairs = pairs[hole[pairs[:, 0]] != hole[pairs[:, 1]]]
    d = np.linalg.norm(xyz[pairs[:, 0]] - xyz[pairs[:, 1]], axis=1)
    same = labels[pairs[:, 0]] == labels[pairs[:, 1]]
    b = np.digitize(d, edges) - 1
    p = pd.Series(labels).value_counts(normalize=True).to_numpy()
    rows = [{"d_from": edges[i], "d_to": edges[i + 1], "n_pairs": int((b == i).sum()),
             "agree": float(same[b == i].mean()) if (b == i).any() else np.nan}
            for i in range(len(edges) - 1)]
    out = pd.DataFrame(rows)
    out["chance"] = float((p ** 2).sum())
    return out


def section_coords(x, y, origin: tuple[float, float], az: float) -> tuple[np.ndarray, np.ndarray]:
    """Distance along a section line of azimuth `az` from `origin`, and signed offset from it
    (positive to the left when looking along `az`)."""
    a = np.deg2rad(az)
    dx, dy = np.asarray(x, float) - origin[0], np.asarray(y, float) - origin[1]
    along = dx * np.sin(a) + dy * np.cos(a)
    off = -dx * np.cos(a) + dy * np.sin(a)
    return along, off
