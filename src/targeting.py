"""ML-6: drill targeting by Gaussian process = kriging (AGENTS.md §6 task 6).

log10 Au on 2 m regularised composites is modelled as a stationary Gaussian process with an
anisotropic Matérn covariance in a rotated frame (along strike θ, across strike, vertical)
plus a White nugget. With `normalize_y` the posterior mean is simple kriging with the sample
mean as the known mean: weights = K⁻¹ k*, the kriging system. The posterior variance depends on
the sample locations only, not on the values, so the variance after a hypothetical hole is
exact before it is drilled ("kriging believer" batch design).

Candidate holes are straight traces scored on new rock (points away from every sample): expected
metres above the cutoff (exploitation) or optimistic metres with the upper confidence bound
u = μ + κσ (latent field) above it (exploration).

Azimuths are degrees clockwise from grid north; dips negative downward (desurvey convention).
"""
import numpy as np
import pandas as pd
from scipy.linalg import cho_solve, cholesky, solve_triangular
from scipy.spatial import cKDTree
from scipy.stats import norm
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, Matern, WhiteKernel

from src import desurvey

LS_BOUNDS = (5.0, 1000.0)
CHUNK = 20000


# --- data -----------------------------------------------------------------------------
def regularise(seg: np.ndarray, rows_per_block: int = 2) -> np.ndarray:
    """Block id per row: consecutive rows within one segment grouped `rows_per_block` at a time
    (1 m composites → 2 m). A short last block keeps its rows. Rows not ok (seg < 0) get −1."""
    seg = np.asarray(seg)
    out = np.full(len(seg), -1)
    ok = seg >= 0
    s = pd.Series(seg[ok])
    rank = s.groupby(s, sort=False).cumcount().to_numpy()
    out[ok] = np.cumsum(rank % rows_per_block == 0) - 1
    return out


def block_mean(block: np.ndarray, A: np.ndarray) -> np.ndarray:
    """Mean of the rows of A (n × p) per block id (≥ 0), in block-id order."""
    b = np.asarray(block)
    ok = b >= 0
    n = b[ok].max() + 1
    A = np.asarray(A, float).reshape(len(b), -1)[ok]
    s = np.zeros((n, A.shape[1]))
    np.add.at(s, b[ok], A)
    return s / np.bincount(b[ok], minlength=n)[:, None]


# --- geometry ---------------------------------------------------------------------------
def frame(az: float) -> np.ndarray:
    """3 × 3 orthonormal matrix whose rows are: along azimuth az (horizontal), across it
    (horizontal, az + 90), vertical up."""
    a = np.deg2rad(az)
    return np.array([[np.sin(a), np.cos(a), 0.0],
                     [np.cos(a), -np.sin(a), 0.0],
                     [0.0, 0.0, 1.0]])


def rotate3d(xyz: np.ndarray, az: float | None, origin: np.ndarray) -> np.ndarray:
    """Coordinates relative to `origin` in the strike frame (az None = unrotated)."""
    d = np.asarray(xyz, float) - origin
    return d if az is None else d @ frame(az).T


def trace(collar_xyz, dip: float, az: float, length: float, step: float = 2.0) -> np.ndarray:
    """Points at step/2, 3·step/2, … along a straight hole (midpoints of `step` intervals)."""
    t = np.arange(step / 2, length, step)
    u = desurvey.unit_vectors(np.array([dip]), np.array([az]))[0]
    return np.asarray(collar_xyz, float) + t[:, None] * u


# --- kernel and fit ---------------------------------------------------------------------
def kernel(aniso: bool, nu: float | None = 1.5, ls0=(150.0, 50.0, 80.0), nested: bool = False):
    """Constant × Matérn(ν) (or RBF when nu is None) + White. aniso: 3 length scales.
    nested: a short and a long structure (nested variogram), each Constant × Matérn."""
    def core(ls, bounds):
        ls = list(ls) if aniso else float(np.mean(ls))
        return RBF(ls, bounds) if nu is None else Matern(ls, bounds, nu=nu)
    if nested:
        lat = (ConstantKernel(0.5, (1e-2, 1e2)) * core((15.0, 10.0, 8.0), (2.0, 1000.0))
               + ConstantKernel(0.5, (1e-2, 1e2)) * core(ls0, (20.0, 3000.0)))
    else:
        lat = ConstantKernel(1.0, (1e-2, 1e2)) * core(ls0, LS_BOUNDS)
    return lat + WhiteKernel(0.3, (1e-3, 1e1))


def fit(X: np.ndarray, y: np.ndarray, k, restarts: int = 3, seed: int = 0) -> GaussianProcessRegressor:
    return GaussianProcessRegressor(k, normalize_y=True, n_restarts_optimizer=restarts,
                                    random_state=seed).fit(X, y)


def nugget(gp: GaussianProcessRegressor) -> float:
    """White-noise variance in log10 units (de-normalised)."""
    return float(gp.kernel_.k2.noise_level * np.atleast_1d(gp._y_train_std)[0] ** 2)


def sill(gp: GaussianProcessRegressor) -> float:
    """Structured (latent) variance in log10 units."""
    return float(gp.kernel_.k1.diag(np.zeros((1, gp.X_train_.shape[1])))[0]
                 * np.atleast_1d(gp._y_train_std)[0] ** 2)


def length_scales(gp: GaussianProcessRegressor) -> list[list[float]]:
    """Length scales of every Matérn/RBF structure in the latent kernel (short first)."""
    p = gp.kernel_.k1.get_params()
    return [np.atleast_1d(v).round(2).tolist() for k, v in sorted(p.items())
            if k.endswith("length_scale")]


def latent_predict(gp: GaussianProcessRegressor, X: np.ndarray, chunk: int = CHUNK):
    """Mean and SD of the latent (nugget-free) field at X, in chunks."""
    k_lat = gp.kernel_.k1
    ym, ys = np.atleast_1d(gp._y_train_mean)[0], np.atleast_1d(gp._y_train_std)[0]
    mu, sd = np.empty(len(X)), np.empty(len(X))
    for i in range(0, len(X), chunk):
        Q = X[i:i + chunk]
        Ks = k_lat(Q, gp.X_train_)
        v = solve_triangular(gp.L_, Ks.T, lower=True)
        mu[i:i + chunk] = Ks @ gp.alpha_ * ys + ym
        sd[i:i + chunk] = np.sqrt(np.clip(k_lat.diag(Q) - (v ** 2).sum(0), 0, None)) * ys
    return mu, sd


def predictive_scores(y, mu, sd_latent, nug) -> dict:
    """Held-out scores for observed values y: RMSE, mean log predictive density, 90% coverage
    (predictive SD includes the nugget)."""
    s = np.sqrt(sd_latent ** 2 + nug)
    z = (y - mu) / s
    return {"rmse": float(np.sqrt(np.mean((y - mu) ** 2))),
            "mlpd": float(np.mean(norm.logpdf(y, mu, s))),
            "cov90": float(np.mean(np.abs(z) <= norm.ppf(0.95))), "n": int(len(y))}


def kriging_weights(gp: GaussianProcessRegressor, Q: np.ndarray) -> np.ndarray:
    """Simple-kriging weights (n_train × n_query) from the fitted covariance: solve
    (C + nugget·I) w = c*, with C, c* the latent covariance (same scaling cancels)."""
    C = gp.kernel_(gp.X_train_)            # latent + White on the diagonal
    c = gp.kernel_.k1(gp.X_train_, Q)
    return cho_solve((cholesky(C, lower=True), True), c)


def sk_mean(gp: GaussianProcessRegressor, Q: np.ndarray) -> np.ndarray:
    """Simple kriging with the sample mean as the known mean."""
    ym, ys = np.atleast_1d(gp._y_train_mean)[0], np.atleast_1d(gp._y_train_std)[0]
    y = gp.y_train_ * ys + ym            # back to log10 units
    return ym + kriging_weights(gp, Q).T @ (y - ym)


def implied_variogram(gp: GaussianProcessRegressor, h: np.ndarray, axis: int) -> np.ndarray:
    """γ(h) = nugget + sill·(1 − ρ(h)) along one frame axis (0 strike, 1 across, 2 vertical),
    for h > 0, in log10² units."""
    P = np.zeros((len(h), 3))
    P[:, axis] = h
    k_lat = gp.kernel_.k1
    c0 = k_lat.diag(np.zeros((1, 3)))[0]
    ys2 = np.atleast_1d(gp._y_train_std)[0] ** 2
    return nugget(gp) + ys2 * (c0 - k_lat(np.zeros((1, 3)), P)[0])


# --- batch design -----------------------------------------------------------------------
def posterior_sd(gp: GaussianProcessRegressor, X_obs: np.ndarray, Q: np.ndarray,
                 chunk: int = CHUNK) -> np.ndarray:
    """Latent SD at Q given observations at X_obs (training plus pseudo-observations, all with
    the fitted nugget), with the fitted hyperparameters. Values are not needed."""
    k_lat = gp.kernel_.k1
    L = cholesky(gp.kernel_(X_obs), lower=True)
    ys = np.atleast_1d(gp._y_train_std)[0]
    out = np.empty(len(Q))
    for i in range(0, len(Q), chunk):
        q = Q[i:i + chunk]
        v = solve_triangular(L, k_lat(X_obs, q), lower=True)
        out[i:i + chunk] = np.sqrt(np.clip(k_lat.diag(q) - (v ** 2).sum(0), 0, None)) * ys
    return out


def optimistic_metres(u: np.ndarray, hole: np.ndarray, valid: np.ndarray, cut: float,
                      step: float, n_holes: int) -> np.ndarray:
    """Metres per hole with u ≥ cut, counting only valid (in-domain) trace points."""
    hit = (u >= cut) & valid
    return np.bincount(hole, weights=hit.astype(float), minlength=n_holes) * step


def expected_metres(mu, sd, nug, hole, valid, cut, step, n_holes) -> np.ndarray:
    """Expected metres per hole above the cutoff: Σ step · P(value ≥ cut), predictive SD
    including the nugget, over valid points."""
    p = norm.sf((cut - mu) / np.sqrt(sd ** 2 + nug))
    return np.bincount(hole, weights=np.where(valid, p, 0.0), minlength=n_holes) * step


def plausible_variance(mu, sd, hole, valid, cut, kappa, step, n_holes) -> np.ndarray:
    """Σ step · σ² over valid points where the UCB reaches the cutoff (μ + κσ ≥ cut): the kriging
    variance a hole would sample in rock that could still be ore (m · log10²). Unlike optimistic
    metres it does not saturate far from data."""
    w = np.where(valid & (mu + kappa * sd >= cut), sd ** 2, 0.0)
    return np.bincount(hole, weights=w, minlength=n_holes) * step


def greedy_portfolio(gp, X_obs, Q, hole, mu, cut, kappa, step, plan, min_new: float,
                     n_holes: int | None = None, tie_tol: float = 0.01):
    """Pick holes one at a time, one per entry of `plan`: 'harap' = expected metres ≥ cut,
    'ucb' = plausible variance (σ² where μ + κσ ≥ cut). Only new rock counts: trace points at least
    `min_new` m (3D, same frame) from every observation. After each pick its trace joins the
    observations: posterior SD updated (exact, values not needed), mean held ("kriging
    believer"), and its points stop being new rock.
    Far from data plausible variance saturates at the prior (every hole in new rock scores the same),
    so in 'ucb' rounds designs within `tie_tol` (relative) of the best are tied and the one whose
    new-rock points lie closest to the observations wins (it closes a gap between drilled ground).
    Returns picks, per-round scores, and per round (n tied, mean new-rock distance to data per hole)."""
    n_holes = int(hole.max()) + 1 if n_holes is None else n_holes
    nug = nugget(gp)
    eligible = np.ones(n_holes, bool)
    X = np.asarray(X_obs, float)
    picks, rounds, ties = [], [], []
    for kind in plan:
        sd = posterior_sd(gp, X, Q)
        d = cKDTree(X).query(Q)[0]
        new = d >= min_new
        if kind == "harap":
            score = expected_metres(mu, sd, nug, hole, new, cut, step, n_holes)
        else:
            score = plausible_variance(mu, sd, hole, new, cut, kappa, step, n_holes)
        rounds.append(score)
        s = np.where(eligible, score, -np.inf)
        n_new = np.bincount(hole, weights=new.astype(float), minlength=n_holes)
        dist = np.bincount(hole, weights=d * new, minlength=n_holes) / np.maximum(n_new, 1)
        if kind == "harap":
            tied = np.array([int(np.argmax(s))])
        else:
            tied = np.flatnonzero(s >= (1 - tie_tol) * s.max())
        best = int(tied[np.argmin(dist[tied])])
        picks.append(best)
        ties.append((len(tied), dist))
        eligible[best] = False
        X = np.vstack([X, Q[hole == best]])
    return picks, np.array(rounds), ties


# --- domain -----------------------------------------------------------------------------
def in_domain(Q_xyz: np.ndarray, data_xyz: np.ndarray, max_h: float, z_min: float) -> np.ndarray:
    """True where a point lies within max_h (horizontal) of a data point and above z_min."""
    d, _ = cKDTree(np.asarray(data_xyz)[:, :2]).query(np.asarray(Q_xyz)[:, :2])
    return (d <= max_h) & (np.asarray(Q_xyz)[:, 2] >= z_min)
