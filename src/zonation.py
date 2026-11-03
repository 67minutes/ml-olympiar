"""ML-3: surface H/M/L grade zonation (AGENTS.md §6 task 3).

Dequantised log10 element values are robust-scaled (median/MAD) and reduced by PCA; the
first component is a multi-element mineralisation index. Zones are a K=3 Gaussian mixture
on that index, ordered by index mean (Rendah < Sedang < Tinggi). Uncertainty comes from
three sources: the mixture posterior, the lab's reporting steps (dequantisation draws) and
sampling (bootstrap refits of the whole pipeline). The soil index is interpolated with an
anisotropic Gaussian process (kriging), and the direction of greatest continuity is tested
against isotropic fields simulated on the same sample layout, so that the sampling
geometry cannot pose as a structural trend.

Azimuths are degrees clockwise from north, folded to [0, 180).
"""
import numpy as np
import pandas as pd
from scipy.linalg import solve_triangular
from scipy.spatial import cKDTree
from scipy.stats import norm
from sklearn.decomposition import PCA
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.metrics import adjusted_rand_score
from sklearn.mixture import GaussianMixture

from src import thresholds as th

ZONES = ("Rendah", "Sedang", "Tinggi")   # zone id 1, 2, 3
K_ZONES = 3
REG_LOG10 = 0.05                         # ML-1 floor: a uniform 0.05 log10 shift in every element


# --- matrix and index -----------------------------------------------------------------
def log_matrix(V: np.ndarray, rng: np.random.Generator | None = None) -> np.ndarray:
    """log10 of each column, dequantised within its reporting step when `rng` is given."""
    V = np.asarray(V, dtype=float)
    if rng is None:
        return np.log10(V)
    return np.column_stack([th.dequantise(V[:, j], rng) for j in range(V.shape[1])])


def clr(L: np.ndarray) -> np.ndarray:
    """Centred log-ratio of a log matrix (row mean removed); subcomposition caveat applies."""
    return L - L.mean(axis=1, keepdims=True)


def robust_params(L: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    med = np.median(L, axis=0)
    mad = 1.4826 * np.median(np.abs(L - med), axis=0)
    if (mad <= 0).any():
        raise ValueError("a feature has zero MAD; it cannot be robust-scaled")
    return med, mad


class Index:
    """Robust scaling + PCA, with the first component's sign fixed so that the reference
    column (Au, column 0) loads positively. `score` gives PC1, the mineralisation index."""

    def __init__(self, L: np.ndarray, ref: int = 0):
        self.med, self.mad = robust_params(L)
        self.pca = PCA().fit((L - self.med) / self.mad)
        self.sign = 1.0 if self.pca.components_[0, ref] >= 0 else -1.0

    def scores(self, L: np.ndarray) -> np.ndarray:
        return self.pca.transform((L - self.med) / self.mad) * self.sign_vector()

    def score(self, L: np.ndarray) -> np.ndarray:
        return self.scores(L)[:, 0]

    def sign_vector(self) -> np.ndarray:
        s = np.ones(self.pca.n_components_)
        s[0] = self.sign
        return s

    def loadings(self, names) -> pd.DataFrame:
        comp = self.pca.components_ * self.sign_vector()[:, None]
        return pd.DataFrame(comp.T, index=list(names), columns=[f"PC{i + 1}" for i in range(len(comp))])

    def reg_covar(self) -> float:
        """Variance floor on the index: the index change from a uniform REG_LOG10 shift."""
        w = self.pca.components_[0] / self.mad
        return float((REG_LOG10 * np.abs(w).sum()) ** 2)


def horn(Z: np.ndarray, n_perm: int = 200, seed: int = 0, q: float = 95) -> tuple[int, np.ndarray, np.ndarray]:
    """Horn's parallel analysis: keep leading components whose eigenvalue exceeds the q-th
    percentile of eigenvalues from column-permuted data. Returns (n kept, eig, null)."""
    rng = np.random.default_rng(seed)
    eig = PCA().fit(Z).explained_variance_
    null = np.array([PCA().fit(np.column_stack([rng.permutation(Z[:, j]) for j in range(Z.shape[1])]))
                     .explained_variance_ for _ in range(n_perm)])
    thr = np.percentile(null, q, axis=0)
    above = eig > thr
    n = int(np.argmin(above)) if not above.all() else len(eig)
    return n, eig, thr


# --- mixture on the index ---------------------------------------------------------------
def fit_gmm(s: np.ndarray, k: int, reg: float, n_init: int = 10, seed: int = 0) -> GaussianMixture:
    return GaussianMixture(k, n_init=n_init, random_state=seed, reg_covar=reg).fit(np.asarray(s).reshape(-1, 1))


def bic_curve(s: np.ndarray, reg: float, kmax: int = 5, n_init: int = 5, seed: int = 0) -> pd.Series:
    """BIC per K on one index sample; models with a component < th.MIN_COMP_N get +inf."""
    out = {}
    for k in range(1, kmax + 1):
        g = fit_gmm(s, k, reg, n_init, seed)
        out[k] = g.bic(np.asarray(s).reshape(-1, 1)) if th.admissible(g, len(s)) else np.inf
    return pd.Series(out)


def order(g: GaussianMixture) -> np.ndarray:
    """Component indices sorted by mean (zone 1 = lowest index)."""
    return np.argsort(g.means_.ravel())


def posterior(g: GaussianMixture, s: np.ndarray) -> np.ndarray:
    """n × K posterior, columns in zone order (lowest mean first)."""
    return g.predict_proba(np.asarray(s).reshape(-1, 1))[:, order(g)]


def zone_thresholds(g: GaussianMixture) -> list[float]:
    """Index values where adjacent zones' weighted densities cross (NaN = nested pair)."""
    return th.crossings(th.components(g))


def boundaries(g: GaussianMixture, lo: float, hi: float, n: int = 4001) -> list[float]:
    """Index values where the most probable zone changes, scanned over [lo, hi]. Unlike
    density crossings between adjacent means, this also finds a boundary that lies beyond
    a wider component's mean. NaN for a zone that never wins; a ValueError if the zones
    are not ordered along the index (the zonation would not be a grade ranking)."""
    x = np.linspace(lo, hi, n)
    z = zone_ids(posterior(g, x))
    if (np.diff(z) < 0).any():
        raise ValueError("zones are not monotone along the index")
    k = g.n_components
    return [float(x[np.argmax(z > j)]) if (z > j).any() and (z <= j).any() else np.nan for j in range(1, k)]


def zone_ids(P: np.ndarray) -> np.ndarray:
    return np.argmax(P, axis=1) + 1


def stability(full: np.ndarray, boot: np.ndarray) -> np.ndarray:
    """Per sample, the share of bootstrap partitions (rows of `boot`) giving its full zone."""
    return (np.asarray(boot) == np.asarray(full)[None, :]).mean(axis=0)


def boot_ari(full: np.ndarray, boot: np.ndarray) -> np.ndarray:
    return np.array([adjusted_rand_score(full, b) for b in boot])


def cramers_v(a, b) -> float:
    t = pd.crosstab(pd.Series(np.asarray(a)), pd.Series(np.asarray(b))).to_numpy(float)
    if min(t.shape) < 2:
        return np.nan
    n = t.sum()
    e = t.sum(1, keepdims=True) * t.sum(0, keepdims=True) / n
    chi2 = ((t - e) ** 2 / e).sum()
    return float(np.sqrt(chi2 / (n * (min(t.shape) - 1))))


# --- spatial: rotation, directional variogram -------------------------------------------
def rotate(xy: np.ndarray, az: float) -> np.ndarray:
    """Coordinates along azimuth `az` (column 0) and across it (column 1)."""
    a = np.deg2rad(az)
    u = np.array([np.sin(a), np.cos(a)])
    v = np.array([np.cos(a), -np.sin(a)])
    xy = np.asarray(xy, float)
    return np.column_stack([xy @ u, xy @ v])


def pair_geometry(xy: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """All point pairs (i < j): index arrays, distance and azimuth folded to [0, 180)."""
    i, j = np.triu_indices(len(xy), 1)
    d = xy[j] - xy[i]
    dist = np.hypot(d[:, 0], d[:, 1])
    az = np.rad2deg(np.arctan2(d[:, 0], d[:, 1])) % 180
    return np.column_stack([i, j]), dist, az


def dir_variogram(geom, z: np.ndarray, angles, tol: float, edges) -> tuple[np.ndarray, np.ndarray]:
    """Semivariance per direction × lag bin (NaN where a bin has < 10 pairs) and pair counts.
    `geom` comes from pair_geometry so simulations reuse the same pairs."""
    ij, dist, az = geom
    sq = 0.5 * (z[ij[:, 0]] - z[ij[:, 1]]) ** 2
    lag = np.digitize(dist, edges) - 1
    nl = len(edges) - 1
    gam, cnt = np.full((len(angles), nl), np.nan), np.zeros((len(angles), nl), int)
    for a, ang in enumerate(angles):
        dang = np.abs((az - ang + 90) % 180 - 90)
        sel = (dang <= tol) & (lag >= 0) & (lag < nl)
        c = np.bincount(lag[sel], minlength=nl)
        s = np.bincount(lag[sel], weights=sq[sel], minlength=nl)
        cnt[a] = c
        ok = c >= 10
        gam[a, ok] = s[ok] / c[ok]
    return gam, cnt


def anisotropy(gam: np.ndarray, angles, n_lags: int = 3) -> tuple[float, float]:
    """Direction of greatest continuity (lowest mean short-lag semivariance) and the
    ratio min/max of that mean across directions (1 = isotropic, small = strong)."""
    m = np.nanmean(gam[:, :n_lags], axis=1)
    return float(np.asarray(angles)[np.nanargmin(m)]), float(np.nanmin(m) / np.nanmax(m))


def angle_in(az: float, lo: float, hi: float) -> bool:
    return lo <= az % 180 <= hi


# --- Gaussian process (kriging) ---------------------------------------------------------
def gp_kernel(aniso: bool, l0: float = 150.0):
    ls = [l0, l0] if aniso else l0
    return (ConstantKernel(1.0, (1e-2, 1e2)) * RBF(ls, (10.0, 5000.0))
            + WhiteKernel(0.3, (1e-3, 1e1)))


def fit_gp(xy: np.ndarray, z: np.ndarray, az: float | None, seed: int = 0, restarts: int = 3,
           kernel=None, optimizer="fmin_l_bfgs_b") -> GaussianProcessRegressor:
    """GP on coordinates rotated to azimuth `az` (None = isotropic, unrotated)."""
    X = rotate(xy, az) if az is not None else np.asarray(xy, float)
    k = kernel if kernel is not None else gp_kernel(az is not None)
    return GaussianProcessRegressor(k, normalize_y=True, n_restarts_optimizer=restarts,
                                    random_state=seed, optimizer=optimizer).fit(X, z)


def latent_predict(gp: GaussianProcessRegressor, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mean and SD of the latent (noise-free) field at X (already rotated): the White
    (nugget) term is left out of the prior variance at the prediction points."""
    k_lat = gp.kernel_.k1
    Ks = k_lat(X, gp.X_train_)
    mean = Ks @ gp.alpha_
    v = solve_triangular(gp.L_, Ks.T, lower=True)
    var = np.clip(k_lat.diag(X) - (v ** 2).sum(axis=0), 0, None)
    ystd = np.atleast_1d(gp._y_train_std)[0]
    return mean * ystd + np.atleast_1d(gp._y_train_mean)[0], np.sqrt(var) * ystd


def zone_probs(mu: np.ndarray, sd: np.ndarray, t_low: float, t_high: float) -> np.ndarray:
    """P(Rendah), P(Sedang), P(Tinggi) of a Gaussian predictive value given two thresholds."""
    sd = np.maximum(sd, 1e-12)
    p_r = norm.cdf((t_low - mu) / sd)
    p_t = norm.sf((t_high - mu) / sd)
    return np.column_stack([p_r, np.clip(1 - p_r - p_t, 0, 1), p_t])


def grid_mask(xy_samples: np.ndarray, gx: np.ndarray, gy: np.ndarray, max_dist: float) -> np.ndarray:
    """True for grid cells (meshgrid of centres gx × gy) within max_dist of a sample."""
    xx, yy = np.meshgrid(gx, gy)
    d, _ = cKDTree(xy_samples).query(np.column_stack([xx.ravel(), yy.ravel()]))
    return (d <= max_dist).reshape(xx.shape)


def simulate_isotropic(xy: np.ndarray, kernel, n: int, seed: int = 0) -> np.ndarray:
    """n Gaussian fields at the sample points from a fitted (isotropic) kernel: n × points."""
    K = kernel(np.asarray(xy, float))
    L = np.linalg.cholesky(K + 1e-10 * np.eye(len(K)))
    return (L @ np.random.default_rng(seed).standard_normal((len(K), n))).T
