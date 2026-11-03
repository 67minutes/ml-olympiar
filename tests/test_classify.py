import numpy as np
import pandas as pd

from src import classify as cl


def synthetic(n_groups=6, per=60, seed=0):
    """Two classes separated on feature a; groups are blocks of rows."""
    rng = np.random.default_rng(seed)
    g = np.repeat([f"G{i}" for i in range(n_groups)], per)
    y = rng.choice(["P", "Q"], len(g))
    a = np.where(y == "P", 0.0, 1.5) + rng.normal(0, 0.5, len(g))
    X = pd.DataFrame({"a": a, "b": rng.normal(0, 1, len(g))})
    return X, pd.Series(y, dtype=object), pd.Series(g)


def run(X, y, g, kind="rf", leaf=5, folds=None):
    classes = sorted(pd.unique(y.dropna()))
    res = [cl.fold_job(*j) for j in cl.oof_jobs(X, y, g, classes, kind, leaf, folds)]
    return classes, cl.collect(len(X), classes, res)[0]


def test_pad_groups_link_close_collars():
    collar = pd.DataFrame({"SiteID": ["RJDH001", "RJDH002", "RJDH003", "RJDH004"],
                           "EastUTM": [0.0, 10.0, 25.0, 500.0], "NorthUTM": [0.0, 0.0, 0.0, 0.0]})
    p = cl.pad_groups(collar, radius=20)
    assert p["RJDH001"] == p["RJDH002"] == p["RJDH003"] == "P001-002-003"  # chained links
    assert p["RJDH004"] == "P004"


def test_spatial_blocks_share_identical_xy():
    b = cl.spatial_blocks(pd.Series([10.0, 10.0, 160.0]), pd.Series([5.0, 5.0, 5.0]), 150)
    assert b[0] == b[1] != b[2]


def test_log_features_and_complete_mask():
    d = pd.DataFrame({"Au": [1.0, 0.0, 10.0], "Cu": [100.0, 10.0, np.nan], "r": [0.5, 0.2, 0.1]})
    X = cl.log_features(d, {"Au": "Au", "Cu": "Cu"}, [("Cu", "Au")], raw={"r": "r"})
    assert np.isclose(X.loc[0, "Cu/Au"], 2.0) and np.isnan(X.loc[1, "Au"])  # 0 -> NaN, not -inf
    assert cl.complete(X).tolist() == [True, False, False]


def test_oof_each_row_once_no_group_leak_and_unlabelled_predicted():
    X, y, g = synthetic()
    y.iloc[:30] = None                       # unlabelled rows inside group G0
    jobs = cl.oof_jobs(X, y, g, ["P", "Q"], "rf", 5)
    for _X, _y, ga, train, test, *_ in jobs:
        assert not set(ga[train]) & set(ga[test])
        assert not train[:30].any()          # unlabelled never trained on
    classes, P = run(X, y, g)
    assert not np.isnan(P).any() and np.allclose(P.sum(axis=1), 1)
    s = cl.scores(y.iloc[30:].to_numpy(), P[30:], classes)
    assert s["bal_acc"] > 0.8 and 0 <= s["pr_auc"] <= 1


def test_deterministic_and_block_folds():
    X, y, g = synthetic(n_groups=10)
    folds = cl.group_folds(g, 5)
    assert sorted(set().union(*folds)) == sorted(g.unique()) and sum(map(len, folds)) == 10
    _, P1 = run(X, y, g, folds=folds)
    _, P2 = run(X, y, g, folds=folds)
    assert np.array_equal(P1, P2)


def test_missing_class_in_training_gets_zero_probability():
    X, y, g = synthetic()
    y[g.eq("G5")] = "R"                      # class only present in one group
    classes, P = run(X, y, g, kind="logreg")
    assert np.allclose(P[g.eq("G5").to_numpy(), classes.index("R")], 0)


def test_tune_leaf_and_dummy_baseline():
    X, y, g = synthetic()
    leaf = cl.tune_leaf(X.to_numpy(), y.to_numpy(object), g.to_numpy(object), grid=(1, 20))
    assert leaf in (1, 20)
    classes, P = run(X, y, g, kind="dummy")
    assert np.isclose(cl.scores(y.to_numpy(), P, classes)["bal_acc"], 0.5)


def test_bootstrap_entropy_reliability_runs():
    y = np.array(["P"] * 50 + ["Q"] * 50, dtype=object)
    lo, hi = cl.group_bootstrap(y, y, np.repeat(np.arange(10), 10), B=50)
    assert lo == hi == 1.0
    P = np.array([[0.5, 0.5], [1.0, 0.0]])
    assert np.allclose(cl.entropy(P), [1.0, 0.0], atol=1e-6)
    rel = cl.reliability(np.array(["P", "P"], dtype=object), P, ["P", "Q"])
    assert rel.n.sum() == 2
    d = pd.DataFrame({"SiteID": ["H"] * 5, "DepthFrom": [0, 1, 2, 4, 5.0], "DepthTo": [1, 2, 3, 5, 6.0],
                      "logged": ["AA"] * 5, "predicted": ["SI"] * 5, "p": [0.8] * 5})
    runs = cl.disagreement_runs(d, pd.Series(True, index=d.index), min_len=3)
    assert runs[["from", "to", "n"]].values.tolist() == [[0, 3, 3]]  # gap at 3–4 m splits; 4–6 m too short
