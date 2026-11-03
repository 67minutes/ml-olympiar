import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor

from src import desurvey, targeting as tg


def small_gp(seed=0, n=80):
    rng = np.random.default_rng(seed)
    X = rng.uniform(0, 200, (n, 3))
    y = np.sin(X[:, 0] / 40) + 0.3 * np.cos(X[:, 2] / 30) + rng.normal(0, 0.1, n)
    return tg.fit(X, y, tg.kernel(True), restarts=0), X, y, rng


def test_regularise_pairs_within_segments():
    seg = np.array([0, 0, 0, -1, 1, 1, 1, 1, 2])
    b = tg.regularise(seg)
    assert b.tolist() == [0, 0, 1, -1, 2, 2, 3, 3, 4]
    m = tg.block_mean(b, np.arange(9, dtype=float))
    assert m.ravel().tolist() == [0.5, 2.0, 4.5, 6.5, 8.0]


def test_frame_orthonormal_and_strike_axis():
    for az in (0, 45, 75, 135):
        R = tg.frame(az)
        assert np.allclose(R @ R.T, np.eye(3))
    # a point 10 m along azimuth 45 lies on the strike axis only
    p = 10 * np.array([np.sin(np.pi / 4), np.cos(np.pi / 4), 0.0])
    assert np.allclose(tg.rotate3d(p[None], 45, np.zeros(3)), [[10, 0, 0]])


def test_trace_matches_desurvey_straight_hole():
    collar = np.array([1000.0, 2000.0, 500.0])
    pts = tg.trace(collar, -60, 315, 200, step=2)
    assert len(pts) == 100
    u = desurvey.unit_vectors(np.array([-60.0]), np.array([315.0]))[0]
    assert np.allclose(pts[-1], collar + 199 * u)
    assert np.isclose(np.linalg.norm(pts[-1] - pts[0]), 198)


def test_simple_kriging_equals_gp_mean():
    gp, X, y, rng = small_gp()
    Q = rng.uniform(0, 200, (25, 3))
    mu, _ = tg.latent_predict(gp, Q)
    assert np.allclose(tg.sk_mean(gp, Q), mu, atol=1e-6)
    assert np.allclose(mu, gp.predict(Q), atol=1e-8)


def test_variance_update_independent_of_values():
    gp, X, y, rng = small_gp()
    Q = rng.uniform(0, 200, (30, 3))
    _, sd0 = tg.latent_predict(gp, Q)
    assert np.allclose(tg.posterior_sd(gp, X, Q), sd0, atol=1e-8)
    # same covariance, shuffled values (same mean and SD): same posterior SD, different mean
    gp2 = GaussianProcessRegressor(gp.kernel_, optimizer=None, normalize_y=True).fit(X, rng.permutation(y))
    mu2, sd2 = tg.latent_predict(gp2, Q)
    assert np.allclose(sd2, sd0, atol=1e-8)
    assert not np.allclose(mu2, tg.latent_predict(gp, Q)[0])
    # new observations never raise the SD
    extra = rng.uniform(0, 200, (10, 3))
    assert np.all(tg.posterior_sd(gp, np.vstack([X, extra]), Q) <= sd0 + 1e-10)


def test_greedy_pick_lowers_sd_and_avoids_repeat():
    gp, X, y, rng = small_gp()
    holes = [tg.trace(np.array([x, 100.0, 210.0]), -90, 0, 100, step=5) for x in (20, 25, 180)]
    Q = np.vstack(holes)
    hole = np.repeat(np.arange(3), [len(h) for h in holes])
    valid = np.ones(len(Q), bool)
    mu, _ = tg.latent_predict(gp, Q)
    picks, rounds, _ = tg.greedy_portfolio(gp, X, Q, hole, mu, cut=-10, kappa=2, step=5,
                                           plan=["harap", "ucb"], min_new=0.0)
    assert len(set(picks)) == 2 and rounds.shape == (2, 3)
    # with a cutoff everyone passes, the score is new-rock metres: hole 1 sits next to hole 0,
    # so after picking hole 0 or 1 the other loses the points within 20 m
    _, r2, _ = tg.greedy_portfolio(gp, X, Q, hole, mu, cut=-10, kappa=2, step=5, plan=["ucb", "ucb"], min_new=20.0)
    assert r2[1].sum() < r2[0].sum()
    sd_before = tg.posterior_sd(gp, X, Q)
    sd_after = tg.posterior_sd(gp, np.vstack([X, Q[hole == picks[0]]]), Q)
    assert sd_after.sum() < sd_before.sum()


def test_ucb_tie_goes_to_hole_nearest_data():
    gp, X, y, rng = small_gp()
    # two holes far outside the data (score at the prior cap, tied); the nearer one must win
    holes = [tg.trace(np.array([x, 100.0, 150.0]), -90, 0, 60, step=5) for x in (900.0, 600.0)]
    Q = np.vstack(holes)
    hole = np.repeat(np.arange(2), [len(h) for h in holes])
    mu, _ = tg.latent_predict(gp, Q)
    picks, rounds, ties = tg.greedy_portfolio(gp, X, Q, hole, mu, cut=-10, kappa=2, step=5,
                                              plan=["ucb"], min_new=20.0)
    assert np.isclose(rounds[0, 0], rounds[0, 1])
    assert picks == [1] and ties[0][0] == 2


def test_optimistic_metres_counts_valid_only():
    u = np.array([1.0, -1.0, 2.0, 2.0])
    hole = np.array([0, 0, 1, 1])
    valid = np.array([True, True, True, False])
    assert tg.optimistic_metres(u, hole, valid, 0.0, 2.0, 2).tolist() == [2.0, 2.0]


def test_in_domain_horizontal_and_depth():
    data = np.array([[0.0, 0.0, 100.0]])
    Q = np.array([[50.0, 0.0, 100.0], [150.0, 0.0, 100.0], [0.0, 0.0, 10.0]])
    assert tg.in_domain(Q, data, 100, 50).tolist() == [True, False, False]


def test_implied_variogram_rises_to_sill():
    gp, *_ = small_gp()
    g = tg.implied_variogram(gp, np.array([1e-6, 1e4]), 0)
    assert np.isclose(g[0], tg.nugget(gp), rtol=1e-3)
    assert np.isclose(g[1], tg.nugget(gp) + tg.sill(gp), rtol=1e-3)


def test_nested_kernel_kriging_and_variogram():
    rng = np.random.default_rng(3)
    X = rng.uniform(0, 200, (60, 3))
    y = np.sin(X[:, 0] / 40) + rng.normal(0, 0.2, 60)
    gp = tg.fit(X, y, tg.kernel(True, nested=True), restarts=0)
    Q = rng.uniform(0, 200, (10, 3))
    assert np.allclose(tg.sk_mean(gp, Q), tg.latent_predict(gp, Q)[0], atol=1e-6)
    g = tg.implied_variogram(gp, np.array([1e-6, 1e5]), 2)
    assert np.isclose(g[1], tg.nugget(gp) + tg.sill(gp), rtol=1e-3)
    assert len(tg.length_scales(gp)) == 2
