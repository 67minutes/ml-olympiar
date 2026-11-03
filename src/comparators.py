"""AGENTS.md §9 literature comparators: a Jansson-style baseline (clr → robust PCA → k-means, elbow)
and a downhole smoother of class probabilities (simplified analogue of the Fontana workflow)."""
import numpy as np
from sklearn.cluster import KMeans
from sklearn.covariance import MinCovDet

SEED = 0
VAR_TARGET = 0.80
MAX_PC = 3


# --- Jansson-style baseline -------------------------------------------------------------
def ilr_basis(D: int) -> np.ndarray:
    """Orthonormal (D, D-1) basis of the clr hyperplane (Helmert contrasts)."""
    V = np.zeros((D, D - 1))
    for j in range(1, D):
        V[:j, j - 1] = 1.0 / j
        V[j, j - 1] = -1.0
        V[:, j - 1] *= np.sqrt(j / (j + 1))
    return V


def ilr_from_log(L: np.ndarray) -> np.ndarray:
    """ilr coordinates of a log matrix. ilr is an isometry of clr, so distances, PCA scores (up to a
    rotation) and k-means partitions are those of clr; it avoids clr's singular covariance in MCD."""
    C = L - L.mean(axis=1, keepdims=True)
    return C @ ilr_basis(L.shape[1])


class RobustPCA:
    """PCA of the MCD covariance; keeps the fewest PCs reaching VAR_TARGET of the robust variance
    (at most MAX_PC)."""

    def __init__(self, Z: np.ndarray, seed: int = SEED, var_target: float = VAR_TARGET, max_pc: int = MAX_PC):
        mcd = MinCovDet(random_state=seed).fit(Z)
        val, vec = np.linalg.eigh(mcd.covariance_)
        o = np.argsort(val)[::-1]
        self.loc, self.val, self.vec = mcd.location_, val[o], vec[:, o]
        self.evr = self.val / self.val.sum()
        self.n_pc = int(min(np.searchsorted(np.cumsum(self.evr), var_target - 1e-12) + 1, max_pc, Z.shape[1]))

    def transform(self, Z: np.ndarray) -> np.ndarray:
        return (Z - self.loc) @ self.vec[:, :self.n_pc]


def kmeans(T: np.ndarray, k: int, seed: int = SEED, n_init: int = 20) -> KMeans:
    return KMeans(k, n_init=n_init, random_state=seed).fit(T)


def wcss_curve(T: np.ndarray, ks=range(2, 11), seed: int = SEED) -> dict[int, float]:
    return {k: float(kmeans(T, k, seed).inertia_) for k in ks}


def elbow(curve: dict[int, float]) -> int:
    """Stated rule: the k whose point lies farthest from the chord joining the first and last points
    of the WCSS curve (both axes scaled to [0, 1])."""
    k = np.array(list(curve), float)
    w = np.array(list(curve.values()), float)
    x = (k - k[0]) / (k[-1] - k[0])
    y = (w - w.min()) / (w.max() - w.min()) if w.max() > w.min() else np.zeros_like(w)
    dx, dy = x[-1] - x[0], y[-1] - y[0]
    d = np.abs(dx * (y - y[0]) - dy * (x - x[0])) / np.hypot(dx, dy)
    return int(k[np.argmax(d)])


def order_by(labels: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Relabel clusters 1..k by increasing median of `ref` (e.g. log Au or log S)."""
    u = np.unique(labels)
    med = [np.median(ref[labels == c]) for c in u]
    m = {c: i + 1 for i, c in enumerate(u[np.argsort(med, kind="stable")])}
    return np.array([m[c] for c in labels])


# --- downhole smoother --------------------------------------------------------------------
def smooth_probs(P: np.ndarray, seg: np.ndarray, w: int) -> np.ndarray:
    """Centred moving average of class probabilities over w rows (odd), within each contiguous
    segment only (window truncated at segment ends); rows with seg < 0 are left as they are."""
    if w <= 1:
        return P.copy()
    h = w // 2
    out = P.copy()
    for s in np.unique(seg[seg >= 0]):
        i = np.flatnonzero(seg == s)
        c = np.vstack([np.zeros(P.shape[1]), np.cumsum(P[i], axis=0)])
        lo = np.clip(np.arange(len(i)) - h, 0, len(i))
        hi = np.clip(np.arange(len(i)) + h + 1, 0, len(i))
        out[i] = (c[hi] - c[lo]) / (hi - lo)[:, None]
    return out
