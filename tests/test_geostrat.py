import numpy as np
from sklearn.metrics import adjusted_rand_score

from src import geostrat as gs


def two_state_sequences(rng, n_seq=6, n=150, stay=0.97):
    X, z = [], []
    for _ in range(n_seq):
        s = 0
        for _ in range(n):
            z.append(s)
            X.append(rng.normal([-2.0, 0.0] if s == 0 else [2.0, 1.0], 0.6))
            if rng.random() > stay:
                s = 1 - s
    return np.array(X), np.array(z), np.full(n_seq, n)


def test_two_state_hmm_recovered():
    rng = np.random.default_rng(0)
    X, z, lens = two_state_sequences(rng)
    m = gs.fit_hmm(X, lens, 2, 1e-3, restarts=3)
    lab = m.predict(X, lens)
    assert adjusted_rand_score(z, lab) > 0.9
    assert np.all(np.diag(m.transmat_) > 0.9)
    assert np.all(gs.run_length(m.transmat_) > 10)


def test_segments_break_at_holes_and_gaps():
    site = np.array(["A"] * 5 + ["B"] * 4)
    ok = np.array([1, 1, 0, 1, 1, 1, 1, 0, 1], bool)
    seg = gs.segments(site, ok)
    assert seg.tolist() == [0, 0, -1, 1, 1, 2, 2, -1, 3]
    assert gs.lengths(seg).tolist() == [2, 2, 2, 1]


def test_censored_spread_within_bounds():
    rng = np.random.default_rng(1)
    V = np.array([[0.25, 3.37]] * 500)
    cens = np.array([[True, False]] * 500)
    L = gs.log_features(V, cens, np.array([0.5, 1.0]), rng)
    lo, hi = np.log10(0.5 / 3), np.log10(0.5)
    assert L[:, 0].min() >= lo and L[:, 0].max() <= hi and L[:, 0].std() > 0.1
    assert np.allclose(L[:, 1], np.log10(3.37), atol=0.002)


def test_align_inverts_permutation():
    rng = np.random.default_rng(2)
    ref = rng.normal(size=(5, 3)) * 5
    perm = np.array([3, 0, 4, 1, 2])
    shuffled = np.empty_like(ref)
    shuffled[perm] = ref                       # state i of ref sits at row perm[i]
    assert gs.align(ref, shuffled + 0.01).tolist() == perm.tolist()
    assert gs.order(np.array([[2.0], [-1.0], [0.5]])).tolist() == [1, 2, 0]


def test_switch_rate_counts_within_segments_only():
    lab = ["a", "a", "b", None, "b", "c", "c"]
    seg = np.array([0, 0, 0, 0, 1, 1, 1])
    # pairs: aa, ab (segment 0, None skipped twice); bc, cc in segment 1; boundary skipped
    assert gs.switch_rate(lab, seg) == 100 * 2 / 4


def test_collapse_repeats():
    V = np.array([[1.0], [1.0], [1.0], [2.0], [2.0]])
    seg = np.array([0, 0, 0, 0, 1])
    shared = np.array([True, True, True, False, True])
    assert gs.collapse_repeats(V, seg, shared).tolist() == [True, False, False, True, True]


def test_section_coords():
    along, off = gs.section_coords([1.0, -1.0], [-1.0, 1.0], (0.0, 0.0), 135)
    assert np.allclose(along, [np.sqrt(2), -np.sqrt(2)]) and np.allclose(off, [0, 0])
    along, off = gs.section_coords([1.0], [1.0], (0.0, 0.0), 135)   # NE of origin: left looking SE
    assert np.allclose(along, 0) and np.allclose(off, np.sqrt(2))


def test_pair_agreement_chance_and_bins():
    xyz = np.array([[0, 0, 0], [5, 0, 0], [0, 15, 0], [100, 0, 0]], float)
    lab = np.array([1, 1, 2, 1])
    hole = np.array(["A", "B", "C", "D"])
    t = gs.pair_agreement(xyz, lab, hole, [0, 10, 20])
    assert t.n_pairs.tolist() == [1, 2] and t.agree.tolist() == [1.0, 0.0]
    assert np.isclose(t.chance.iloc[0], 0.75 ** 2 + 0.25 ** 2)


def test_run_label_rows_marks_middle_of_long_runs():
    st = np.array([1, 1, 1, 1, 1, 2, 2, 3, 3, 3])
    seg = np.array([0] * 7 + [1] * 3)
    assert np.flatnonzero(gs.run_label_rows(st, seg, 3)).tolist() == [2, 8]
