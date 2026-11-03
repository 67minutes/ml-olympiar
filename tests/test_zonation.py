import numpy as np
import pytest

from src import zonation as zn


def three_groups(rng, sep=3.0, n=100):
    return np.concatenate([rng.normal(-sep, 0.5, n), rng.normal(0, 0.5, n), rng.normal(sep, 0.5, n)])


def test_three_groups_recovered_and_ordered():
    rng = np.random.default_rng(0)
    s = three_groups(rng)
    g = zn.fit_gmm(s, 3, 1e-4)
    P = zn.posterior(g, s)
    assert np.allclose(P.sum(axis=1), 1)
    z = zn.zone_ids(P)
    assert (z[:100] == 1).mean() > 0.95 and (z[100:200] == 2).mean() > 0.95 and (z[200:] == 3).mean() > 0.95
    t = zn.zone_thresholds(g)
    assert len(t) == 2 and -3 < t[0] < 0 < t[1] < 3
    assert zn.bic_curve(s, 1e-4, kmax=5).idxmin() == 3


def test_zone_order_is_label_invariant():
    rng = np.random.default_rng(1)
    s = three_groups(rng)
    a = zn.zone_ids(zn.posterior(zn.fit_gmm(s, 3, 1e-4, seed=0), s))
    b = zn.zone_ids(zn.posterior(zn.fit_gmm(s, 3, 1e-4, seed=7, n_init=1), s))
    assert (a == b).mean() > 0.99   # same zones whatever internal component labels


def test_stability_high_when_separated_low_when_overlapping():
    rng = np.random.default_rng(2)
    full = np.repeat([1, 2, 3], 50)
    same = np.tile(full, (20, 1))
    assert np.allclose(zn.stability(full, same), 1) and np.allclose(zn.boot_ari(full, same), 1)
    noisy = np.where(rng.random((20, 150)) < 0.4, rng.integers(1, 4, (20, 150)), full)
    st = zn.stability(full, noisy)
    assert 0.5 < st.mean() < 0.9


def test_horn_keeps_one_component_on_one_factor_data():
    rng = np.random.default_rng(3)
    f = rng.normal(size=(300, 1))
    Z = f @ np.ones((1, 6)) + 0.5 * rng.normal(size=(300, 6))
    n, eig, thr = zn.horn(Z, n_perm=50)
    assert n == 1 and eig[0] > thr[0] and eig[1] < thr[1]


def test_index_sign_follows_reference_column():
    rng = np.random.default_rng(4)
    f = rng.normal(size=200)
    L = np.column_stack([f, f + 0.1 * rng.normal(size=200), -f + 0.1 * rng.normal(size=200)])
    idx = zn.Index(L, ref=0)
    assert np.corrcoef(idx.score(L), L[:, 0])[0, 1] > 0.9
    assert idx.loadings(["a", "b", "c"]).loc["a", "PC1"] > 0
    assert idx.reg_covar() > 0


def test_rotate_and_variogram_recover_anisotropy():
    assert np.allclose(zn.rotate(np.array([[0.0, 1.0]]), 0), [[1, 0]])      # north along az 0
    assert np.allclose(zn.rotate(np.array([[1.0, 0.0]]), 90), [[1, 0]])     # east along az 90
    rng = np.random.default_rng(5)
    xy = rng.uniform(0, 1000, (400, 2))
    # long range along azimuth 45, short across: field varies with the across-coordinate
    z = np.sin(zn.rotate(xy, 45)[:, 1] / 60) + 0.05 * rng.normal(size=400)
    angles = np.arange(0, 180, 15)
    geom = zn.pair_geometry(xy)
    gam, cnt = zn.dir_variogram(geom, z, angles, 22.5, 20 + 40 * np.arange(11))
    az, ratio = zn.anisotropy(gam, angles)
    assert az in (30, 45, 60) and ratio < 0.5
    assert cnt.sum() > 0 and zn.angle_in(az, 30, 60)


def test_grid_mask_distance_rule():
    pts = np.array([[0.0, 0.0]])
    gx = gy = np.array([-100.0, 0.0, 50.0, 70.0])
    m = zn.grid_mask(pts, gx, gy, 60)
    assert m[1, 1] and m[1, 2] and not m[1, 3] and not m[0, 0]


def test_zone_probs_sum_to_one_and_follow_mean():
    p = zn.zone_probs(np.array([-5.0, 0.0, 5.0]), np.array([0.5, 0.5, 0.5]), -1, 1)
    assert np.allclose(p.sum(axis=1), 1)
    assert np.argmax(p, axis=1).tolist() == [0, 1, 2]


def test_gp_latent_sd_below_predictive_sd():
    rng = np.random.default_rng(6)
    xy = rng.uniform(0, 500, (60, 2))
    z = np.sin(xy[:, 0] / 100) + 0.3 * rng.normal(size=60)
    gp = zn.fit_gp(xy, z, az=30, restarts=0)
    X = zn.rotate(xy[:5], 30)
    mu, sd = zn.latent_predict(gp, X)
    mu2, sd2 = gp.predict(X, return_std=True)
    assert np.allclose(mu, mu2) and (sd < sd2).all()


def test_cramers_v_bounds():
    a = np.repeat([0, 1], 50)
    assert zn.cramers_v(a, a) == pytest.approx(1.0)
    assert zn.cramers_v(a, np.tile([0, 1], 50)) < 0.05


def test_boundaries_find_cut_beyond_wide_component_mean():
    rng = np.random.default_rng(7)
    s = np.concatenate([rng.normal(-1, 1.0, 300), rng.normal(1, 1.0, 200), rng.normal(2.5, 1.6, 60)])
    g = zn.fit_gmm(s, 3, 1e-3)
    t = zn.boundaries(g, s.min() - 0.5, s.max() + 0.5)
    z = zn.zone_ids(zn.posterior(g, s))
    for j, tj in enumerate(t, start=1):
        if np.isfinite(tj):
            assert (s[z <= j] < tj + 1e-3).all() and (s[z > j] >= tj - 1e-3).all()
    sep = three_groups(rng)
    assert len(zn.boundaries(zn.fit_gmm(sep, 3, 1e-4), -6, 6)) == 2
