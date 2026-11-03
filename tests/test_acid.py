import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from src import acid


def test_nag_class_edges():
    ph = [4.5, 4.49, 3.0, 3.0, np.nan]
    cap = [0.005, 0.005, 10.0, 9.99, 50.0]
    assert acid.nag_class(ph, cap).tolist() == ["NAF", "PAF-LC", "PAF-HC", "PAF-LC", None]
    assert acid.nag_class([3.0], [9.99], cap_cut=5).tolist() == ["PAF-HC"]


def test_napp_proxy_units():
    d = acid.napp_proxy([1.0], [2.0], [1.0], [0.0])
    assert np.isclose(d.MPA_SCIS[0], 30.6) and np.isclose(d.MPA_total[0], 61.2)
    assert np.isclose(d.ANC_maks[0], 24.47, atol=0.01)
    assert np.isclose(d.NAPP_min_SCIS[0], 30.6 - 24.47, atol=0.01)


def test_depth_blocks():
    assert acid.depth_blocks([0, 9.9, 10, 25], 10).tolist() == [0, 0, 1, 2]


def _toy(rng, n):
    y = rng.integers(0, 3, n)
    X = rng.normal(y[:, None] * np.array([1.0, 0.3]), 1.0)
    return X, np.asarray(acid.CLASSES, dtype=object)[y]


def _cross_conformal(X, y, Xt, k=5):
    folds = np.arange(len(y)) % k
    cal, test = [], []
    for f in range(k):
        m = LogisticRegression(max_iter=1000).fit(X[folds != f], y[folds != f])
        order = [list(m.classes_).index(c) for c in acid.CLASSES]
        cal.append((m.predict_proba(X[folds == f])[:, order], y[folds == f]))
        test.append(m.predict_proba(Xt)[:, order])
    return acid.mondrian_pvalues(cal, test)


def test_mondrian_class_coverage():
    alpha, hits = 0.1, {c: [] for c in acid.CLASSES}
    for seed in range(30):
        rng = np.random.default_rng(seed)
        X, y = _toy(rng, 150)
        Xt, yt = _toy(rng, 60)
        p = _cross_conformal(X, y, Xt)
        assert ((p > 0) & (p <= 1)).all()
        S = acid.prediction_sets(p, alpha)
        for j, c in enumerate(acid.CLASSES):
            hits[c] += S[yt == c, j].tolist()
    for c in acid.CLASSES:
        assert np.mean(hits[c]) >= 1 - alpha - 0.03, c


def test_separated_classes_give_singletons():
    rng = np.random.default_rng(0)
    y = np.repeat(np.asarray(acid.CLASSES, dtype=object), 40)
    X = np.repeat([[0.0], [10.0], [20.0]], 40, axis=0) + rng.normal(0, 0.5, (120, 1))
    p = _cross_conformal(X, y, np.array([[0.0], [10.0], [20.0]]))
    S = acid.prediction_sets(p, 0.1)
    assert S.sum(1).tolist() == [1, 1, 1]
    assert acid.set_label(S).tolist() == ["NAF", "PAF-LC", "PAF-HC"]


def test_manage_is_conservative():
    S = np.array([[1, 1, 0], [1, 0, 0], [0, 1, 1], [0, 0, 0], [0, 0, 0]], bool)
    p = np.array([[.5, .5, 0], [.5, 0, 0], [0, .5, .5], [.09, .01, .02], [.01, .02, .08]])
    assert acid.manage(S, p).tolist() == ["PAF-LC", "NAF", "PAF-HC", "PAF-LC", "PAF-HC"]
    assert acid.set_label(S)[3] == "kosong"


def test_coverage_table():
    S = np.array([[1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0]], bool)
    t = acid.coverage(["NAF", "NAF", "PAF-HC", "PAF-LC"], S).set_index("kelas")
    assert t.loc["NAF", "cakupan"] == 0.5 and t.loc["PAF-HC", "singleton"] == 1.0
    assert t.loc["PAF-LC", "cakupan"] == 0.0 and t.loc["semua", "cakupan"] == 0.5


def test_tier():
    t = acid.tier([1, 1, 1, 0, 0], [0, 0, 0, 1, 0], [0, 1, 0, 0, 0], [0, 0, 1, 0, 0])
    assert t.tolist() == [1, 2, 2, 3, 4]


def test_merge_runs():
    d = pd.DataFrame({"SiteID": ["A"] * 4 + ["B"], "DepthFrom": [0, 1, 2, 4, 0], "DepthTo": [1, 2, 3, 5, 1],
                      "k": ["x", "x", "y", "y", "x"]})
    r = acid.merge_runs(d, ["k"])
    assert r[["from", "to", "n", "k"]].values.tolist() == [[0, 2, 2, "x"], [2, 3, 1, "y"], [4, 5, 1, "y"],
                                                          [0, 1, 1, "x"]]
    assert r.length_m.tolist() == [2, 1, 1, 1]
