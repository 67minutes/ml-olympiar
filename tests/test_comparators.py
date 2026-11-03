import numpy as np

from src import comparators as cp


def test_ilr_is_isometric_to_clr():
    rng = np.random.default_rng(0)
    L = rng.normal(size=(30, 5))
    C = L - L.mean(axis=1, keepdims=True)
    Z = cp.ilr_from_log(L)
    V = cp.ilr_basis(5)
    assert np.allclose(V.T @ V, np.eye(4)) and np.allclose(V.sum(axis=0), 0)
    dc = np.linalg.norm(C[:, None] - C[None], axis=2)
    dz = np.linalg.norm(Z[:, None] - Z[None], axis=2)
    assert np.allclose(dc, dz)


def test_robust_pca_finds_main_axis_despite_outliers():
    rng = np.random.default_rng(1)
    t = rng.normal(size=300)
    Z = np.column_stack([3 * t, 0.3 * rng.normal(size=300), 0.3 * rng.normal(size=300)])
    Z[:15] = [0, 40, 40]   # gross outliers off the main axis
    r = cp.RobustPCA(Z)
    assert abs(r.vec[0, 0]) > 0.99 and r.n_pc == 1
    assert r.transform(Z).shape == (300, 1)


def test_elbow_picks_the_knee():
    curve = {2: 100.0, 3: 40.0, 4: 30.0, 5: 25.0, 6: 22.0, 7: 20.0, 8: 19.0, 9: 18.0, 10: 17.0}
    assert cp.elbow(curve) == 3


def test_order_by_reference_median():
    lab = np.array([5, 5, 2, 2, 9, 9])
    ref = np.array([10.0, 11, 0, 1, 5, 6])
    assert cp.order_by(lab, ref).tolist() == [3, 3, 1, 1, 2, 2]


def test_smooth_probs_stays_within_segments():
    P = np.array([[1, 0], [0, 1], [1, 0], [0, 1], [0, 1], [1, 0]], float)
    seg = np.array([0, 0, 0, 1, 1, -1])
    S = cp.smooth_probs(P, seg, 3)
    assert np.allclose(S.sum(1), 1)
    assert np.allclose(S[0], [0.5, 0.5]) and np.allclose(S[1], [2 / 3, 1 / 3])
    assert np.allclose(S[3], [0, 1]) and np.allclose(S[5], [1, 0])
    assert np.allclose(cp.smooth_probs(P, seg, 1), P)
