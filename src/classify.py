"""ML-2: logged classes (alteration, oxidation, lithology, minerals) from chemistry
(AGENTS.md §6 task 2).

Random forests on log10 element values and log-ratios, validated by leaving out whole
drill pads (twin holes share near-surface geology, so leaving out one hole leaks) or
spatial blocks for surface samples. Every row gets an out-of-fold (OOF) prediction from a
model that never saw its group, so the exported probabilities are honest. Rows without a
label but inside a held-out group (e.g. RJDH019 oxidation) are predicted in that fold.
"""
import warnings

import numpy as np
import pandas as pd
from scipy.sparse.csgraph import connected_components
from scipy.spatial.distance import pdist, squareform
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, balanced_accuracy_score, cohen_kappa_score,
                             confusion_matrix, f1_score)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 0
N_TREES = 300
LEAF_GRID = (1, 5, 20)
INNER_SPLITS = 4
PAD_RADIUS_M = 30.0


# --- groups ------------------------------------------------------------------------
def pad_groups(collar: pd.DataFrame, radius: float = PAD_RADIUS_M) -> pd.Series:
    """SiteID -> pad label: collars linked when closer than `radius` (single linkage),
    labelled by their sorted hole numbers, e.g. 'P005-014'."""
    xy = collar[["EastUTM", "NorthUTM"]].to_numpy(float)
    _, comp = connected_components(squareform(pdist(xy)) < radius, directed=False)
    ids = collar.SiteID.to_numpy()
    name = {c: "P" + "-".join(sorted(s[-3:] for s in ids[comp == c])) for c in np.unique(comp)}
    return pd.Series([name[c] for c in comp], index=ids, name="pad")


def spatial_blocks(x: pd.Series, y: pd.Series, size: float) -> pd.Series:
    """Square grid block label per point (identical coordinates share a block)."""
    bx, by = np.floor(x / size).astype("Int64"), np.floor(y / size).astype("Int64")
    return ("B" + bx.astype(str) + "_" + by.astype(str)).rename("block")


# --- features ----------------------------------------------------------------------
def log_features(d: pd.DataFrame, cols: dict[str, str], ratios: list[tuple[str, str]] = (),
                 raw: dict[str, str] | None = None) -> pd.DataFrame:
    """log10 of positive values (`cols`: feature name -> column), log-ratios between those
    features, and untransformed columns (`raw`). Non-positive values become NaN."""
    out = pd.DataFrame(index=d.index)
    for name, c in cols.items():
        v = pd.to_numeric(d[c], errors="coerce")
        out[name] = np.log10(v.where(v > 0))
    for a, b in ratios:
        out[f"{a}/{b}"] = out[a] - out[b]
    for name, c in (raw or {}).items():
        out[name] = pd.to_numeric(d[c], errors="coerce")
    return out


def complete(X: pd.DataFrame) -> pd.Series:
    """Rows where every feature exists (tiers are fitted on complete rows only)."""
    return X.notna().all(axis=1)


# --- models ------------------------------------------------------------------------
def rf(leaf: int = 1) -> RandomForestClassifier:
    return RandomForestClassifier(n_estimators=N_TREES, min_samples_leaf=leaf, max_features="sqrt",
                                  class_weight="balanced_subsample", random_state=SEED, n_jobs=1)


def logreg():
    return make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=5000))


def dummy() -> DummyClassifier:
    return DummyClassifier(strategy="prior")


MODELS = {"rf": rf, "logreg": logreg, "dummy": dummy}


def _proba(model, X, classes) -> np.ndarray:
    """predict_proba aligned to the full class list (classes absent in training get 0)."""
    p = model.predict_proba(X)
    out = np.zeros((len(X), len(classes)))
    for j, c in enumerate(model.classes_):
        out[:, list(classes).index(c)] = p[:, j]
    return out


def tune_leaf(X: np.ndarray, y: np.ndarray, g: np.ndarray, grid=LEAF_GRID) -> int:
    """min_samples_leaf with the best mean inner GroupKFold balanced accuracy."""
    k = min(INNER_SPLITS, len(np.unique(g)))
    best, best_s = grid[0], -np.inf
    for leaf in grid:
        s = []
        for tr, te in GroupKFold(n_splits=k).split(X, y, g):
            m = rf(leaf).fit(X[tr], y[tr])
            with warnings.catch_warnings():  # a held-out pad may lack some classes
                warnings.simplefilter("ignore", UserWarning)
                s.append(balanced_accuracy_score(y[te], m.predict(X[te])))
        if np.mean(s) > best_s + 1e-12:
            best, best_s = leaf, np.mean(s)
    return best


def fold_job(X, y, g, train, test, classes, kind: str, leaf: int | None):
    """Fit one outer fold; return (test indices, probabilities, chosen leaf)."""
    tr = np.flatnonzero(train)
    if kind == "rf":
        if leaf is None:
            leaf = tune_leaf(X[tr], y[tr], g[tr])
        model = rf(leaf)
    else:
        model = MODELS[kind]()
    model.fit(X[tr], y[tr])
    te = np.flatnonzero(test)
    return te, _proba(model, X[te], classes), leaf


def oof_jobs(X: pd.DataFrame, y: pd.Series, groups: pd.Series, classes, kind: str,
             leaf: int | None = None, folds: list | None = None) -> list[tuple]:
    """Arguments for `fold_job`, one per held-out group (or per given fold list of group
    sets). Training uses labelled rows outside the fold; every row in the fold (labelled
    or not) is predicted. Asserts no group is on both sides."""
    Xa, ya, ga = X.to_numpy(float), y.to_numpy(object), groups.to_numpy(object)
    lab = pd.notna(ya)
    folds = folds if folds is not None else [{u} for u in sorted(pd.unique(ga))]
    jobs = []
    for f in folds:
        test = np.isin(ga, list(f))
        train = lab & ~test
        assert not set(ga[train]) & set(ga[test]), "group on both sides of a fold"
        jobs.append((Xa, np.where(lab, ya, None), ga, train, test, list(classes), kind, leaf))
    return jobs


def collect(n: int, classes, results) -> tuple[np.ndarray, list]:
    """Stack fold results into an n × classes OOF matrix; each row predicted once."""
    P = np.full((n, len(classes)), np.nan)
    seen = np.zeros(n, int)
    leaves = []
    for te, p, leaf in results:
        P[te] = p
        seen[te] += 1
        leaves.append(leaf)
    assert seen.max() <= 1, "row predicted in more than one fold"
    return P, leaves


def group_folds(groups: pd.Series, n_splits: int) -> list[set]:
    """GroupKFold partition of the unique groups (for spatial blocks)."""
    g = groups.to_numpy(object)
    return [set(g[te]) for _, te in GroupKFold(n_splits=n_splits).split(g, g, g)]


# --- scoring -----------------------------------------------------------------------
def predict(P: np.ndarray, classes) -> np.ndarray:
    return np.asarray(classes, dtype=object)[np.nanargmax(P, axis=1)]


def scores(y: np.ndarray, P: np.ndarray, classes) -> dict:
    """Balanced accuracy, macro-F1, Cohen's kappa, per-class recall/precision; PR-AUC
    (positive = last class) for binary targets."""
    yhat = predict(P, classes)
    y = np.asarray(y, dtype=object)
    out = {"n": len(y), "bal_acc": balanced_accuracy_score(y, yhat),
           "macro_f1": f1_score(y, yhat, labels=list(classes), average="macro", zero_division=0),
           "kappa": cohen_kappa_score(y, yhat, labels=list(classes))}
    cm = confusion_matrix(y, yhat, labels=list(classes))
    for i, c in enumerate(classes):
        out[f"recall_{c}"] = cm[i, i] / cm[i].sum() if cm[i].sum() else np.nan
        out[f"precision_{c}"] = cm[i, i] / cm[:, i].sum() if cm[:, i].sum() else np.nan
    if len(classes) == 2:
        out["pr_auc"] = average_precision_score(y == classes[1], P[:, 1])
        out["prevalence"] = float(np.mean(y == classes[1]))
    return out


def group_bootstrap(y, yhat, groups, metric=balanced_accuracy_score, B: int = 1000,
                    seed: int = SEED) -> tuple[float, float]:
    """5–95% interval of `metric` when whole groups are resampled with replacement."""
    y, yhat, g = (np.asarray(a, dtype=object) for a in (y, yhat, groups))
    ug = pd.unique(g)
    idx = {u: np.flatnonzero(g == u) for u in ug}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        take = np.concatenate([idx[u] for u in rng.choice(ug, len(ug), replace=True)])
        if len(set(y[take])) < 2:
            continue
        vals.append(metric(y[take], yhat[take]))
    return tuple(np.percentile(vals, [5, 95]))


def entropy(P: np.ndarray) -> np.ndarray:
    """Shannon entropy normalised to [0, 1] by log(number of classes)."""
    Q = np.clip(P, 1e-12, 1)
    return -(Q * np.log(Q)).sum(axis=1) / np.log(P.shape[1])


def reliability(y, P: np.ndarray, classes, bins: int = 10) -> pd.DataFrame:
    """Top-class confidence vs observed accuracy per confidence bin."""
    conf = P.max(axis=1)
    hit = predict(P, classes) == np.asarray(y, dtype=object)
    b = np.minimum((conf * bins).astype(int), bins - 1)
    df = pd.DataFrame({"bin": b, "conf": conf, "hit": hit})
    return df.groupby("bin").agg(n=("hit", "size"), conf=("conf", "mean"), acc=("hit", "mean")).reset_index()


# --- review list -------------------------------------------------------------------
def disagreement_runs(d: pd.DataFrame, flag: pd.Series, min_len: float) -> pd.DataFrame:
    """Contiguous runs of flagged intervals per hole (sorted by depth; a run continues while
    the next flagged interval starts where the previous ended and predicts the same class).
    `d` needs SiteID, DepthFrom, DepthTo, logged, predicted, p. Runs ≥ min_len metres kept."""
    s = d[flag.reindex(d.index).fillna(False).astype(bool)].sort_values(["SiteID", "DepthFrom"])
    rows, cur = [], None
    for r in s.itertuples():
        if (cur and r.SiteID == cur["SiteID"] and np.isclose(r.DepthFrom, cur["to"])
                and r.predicted == cur["predicted"]):
            cur["to"] = r.DepthTo
            cur["n"] += 1
            cur["p"].append(r.p)
            cur["logged"].add(r.logged)
            continue
        if cur:
            rows.append(cur)
        cur = {"SiteID": r.SiteID, "from": r.DepthFrom, "to": r.DepthTo, "n": 1, "p": [r.p],
               "logged": {r.logged}, "predicted": r.predicted}
    if cur:
        rows.append(cur)
    out = pd.DataFrame([{**c, "length_m": c["to"] - c["from"], "p_mean": float(np.mean(c["p"])),
                         "logged": "/".join(sorted(map(str, c["logged"])))} for c in rows])
    if out.empty:
        return pd.DataFrame(columns=["SiteID", "from", "to", "length_m", "n", "logged", "predicted", "p_mean"])
    out = out[out.length_m >= min_len - 1e-9].round({"from": 2, "to": 2, "length_m": 2, "p_mean": 3})
    return out[["SiteID", "from", "to", "length_m", "n", "logged", "predicted", "p_mean"]].reset_index(drop=True)
