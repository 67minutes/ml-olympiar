"""AGENTS.md §9.2 comparator: simplified analogue of the Fontana et al. workflow (PCA → Random Forest on
downhole samples, class probabilities smoothed downhole) vs our Gaussian HMM (ML-4). Plan: LOG.md,
2026-11-04 entry. It does not replicate CSIRO Data Mosaic; the smoother is a stated, fixed rule.

1 m `comp_ok` composites and the ML-4 features (log10 Au, Ag, Cu, As; dequantisation draw 0). Targets:
logged alteration (ML-2 label set AA/SI/AR/PP) and oxidation. Leave-one-pad-out (12 pads, as ML-2/4):
per outer fold, median/MAD scaling and PCA (all components) fitted on training pads, RF leaf tuned on
training pads (`classify.tune_leaf`), and the smoothing window w ∈ {1, 3, 5, 9, 15, 25, 41} m chosen on
training pads only (inner GroupKFold, balanced accuracy of the smoothed inner out-of-fold labels;
log loss recorded but not used, see the comment in `outer_fold`).
Smoothing = centred moving average of class probabilities within contiguous segments.
Compared with the HMM states: agreement with the logs (balanced accuracy for RF; ARI and Cramér's V
for both), fragmentation (label switches per 100 m, logs as reference), and agreement on the twin pads
005/014, 010/011, 016/017 by 3D distance.
Reads data/interim/06_composites.csv, 03_collar.csv, 01_element_summary.csv,
data/processed/ml/komposit__ml4_hmm.csv; writes data/processed/s9_rf_smoother_{scores,folds,kembar}.csv,
data/processed/ml/komposit__s9_rf.csv, outputs/figures/14_rf_vs_hmm_v1.png.
Run: PYTHONIOENCODING=utf-8 uv run python -W ignore scripts/20_s9_rf_smoother.py  (then scripts/07_export.py)
"""
import importlib.util
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, log_loss
from sklearn.model_selection import GroupKFold

from src import classify, comparators as cp, geostrat as gs, paths, zonation as zn

SEED = 0
WINDOWS = (1, 3, 5, 9, 15, 25, 41)   # 25, 41 added: every fold chose 15 on the planned grid
INNER = 4
CLIP = 1e-3
TWIN_PADS = ("P005-014", "P010-011", "P016-017")
TWIN_EDGES = np.array([0, 10, 20, 50, 100])
TARGETS = {"alterasi": ("alt_ml_label", ["AA", "SI", "AR", "PP"]),
           "oksidasi": ("ox_state", ["Oxide", "Transition", "Sulphide"])}
C_LOG, C_RAW, C_SM, C_HMM = "#0b0b0b", "#b9b8b2", "#52514e", "#2b4c9b"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), paths.ROOT / "scripts" / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def transform(L_tr: np.ndarray, L: np.ndarray) -> np.ndarray:
    med, mad = zn.robust_params(L_tr)
    pca = PCA(random_state=SEED).fit((L_tr - med) / mad)
    return pca.transform((L - med) / mad)


def proba(X_tr, y_tr, X_te, classes, leaf) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return classify._proba(classify.rf(leaf).fit(X_tr, y_tr), X_te, classes)


def loss(y, P, classes) -> float:
    m = pd.notna(y)
    Q = np.clip(P[m], CLIP, 1)
    return log_loss(np.asarray(y, object)[m], Q / Q.sum(1, keepdims=True), labels=classes)


def outer_fold(pad, L, y, pads, seg, classes):
    """One held-out pad: transform, leaf and window from training pads only; raw and smoothed
    probabilities for every row of the held-out pad."""
    tr_all, te = pads != pad, pads == pad
    X = transform(L[tr_all], L)
    lab = pd.notna(y)
    tr = tr_all & lab
    leaf = classify.tune_leaf(X[tr], y[tr], pads[tr])
    # window: inner out-of-fold probabilities over whole training pads (rows kept contiguous)
    P_in = np.full((len(y), len(classes)), np.nan)
    tr_idx = np.flatnonzero(tr_all)
    for _, ite in GroupKFold(n_splits=INNER).split(tr_idx, groups=pads[tr_idx]):
        inner_te = np.zeros(len(y), bool)
        inner_te[tr_idx[ite]] = True
        inner_tr = tr & ~inner_te
        P_in[inner_te] = proba(X[inner_tr], y[inner_tr], X[inner_te], classes, leaf)
    # window by inner balanced accuracy of the smoothed labels (ties -> smaller w). Log loss is kept
    # for the record only: averaging tempers the RF's overconfident probabilities, so it keeps
    # rewarding wider windows even as the labels get worse.
    yt, m = y[tr_all], lab[tr_all]
    crit = {}
    for w_ in WINDOWS:
        S = cp.smooth_probs(P_in[tr_all], seg[tr_all], w_)
        crit[w_] = {"logloss": loss(yt, S, classes),
                    "bal_acc": classify.scores(yt[m], S[m], classes)["bal_acc"]}
    w = max(WINDOWS, key=lambda k: (round(crit[k]["bal_acc"], 6), -k))
    P = proba(X[tr], y[tr], X[te], classes, leaf)
    return pad, np.flatnonzero(te), P, cp.smooth_probs(P, seg[te], w), leaf, w, crit


def agreement(y, lab) -> dict:
    m = pd.notna(y) & pd.notna(lab)
    ya, la = np.asarray(y, object)[m].astype(str), np.asarray(lab, object)[m].astype(str)
    return {"ARI": adjusted_rand_score(ya, la), "V": zn.cramers_v(ya, la), "n": int(m.sum())}


def twins(xyz, lab, site, pads) -> pd.DataFrame:
    parts = []
    for p in TWIN_PADS:
        s = pads == p
        parts.append(gs.pair_agreement(xyz[s], np.asarray(lab, object)[s].astype(str), site[s], TWIN_EDGES))
    t = pd.concat(parts)
    return t.groupby(["d_from", "d_to"]).apply(
        lambda x: pd.Series({"n_pairs": x.n_pairs.sum(),
                             "agree": np.average(x.agree.fillna(0), weights=x.n_pairs) if x.n_pairs.sum() else np.nan,
                             "chance": x.chance.iloc[0]}), include_groups=False).reset_index()


def fig(scores: pd.DataFrame, tw: pd.DataFrame, path):
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.4), gridspec_kw={"width_ratios": [1, 1.25, 1.1]})
    ax = axes[0]
    meth = [("RF mentah", C_RAW), ("RF dihaluskan", C_SM), ("HMM (ML-4)", C_HMM)]
    for j, tgt in enumerate(TARGETS):
        for i, (m, col) in enumerate(meth):
            v = scores.loc[scores.target.eq(tgt) & scores.metode.eq(m), "V"]
            ax.bar(j + (i - 1) * 0.26, v.iloc[0], width=0.24, color=col, label=m if j == 0 else None)
            ax.text(j + (i - 1) * 0.26, v.iloc[0] + 0.01, f"{v.iloc[0]:.2f}", ha="center", fontsize=7)
    ax.set_xticks(range(len(TARGETS)), [f"vs log {t}" for t in TARGETS], fontsize=8.5)
    ax.set_ylabel("Cramér's V terhadap log", fontsize=8.5)
    ax.set_title("Kesesuaian dengan log (validasi per pad)", fontsize=9.5)
    ax.set_ylim(0, scores.V.max() * 1.3)
    ax.legend(fontsize=7.5, frameon=False, loc="upper center", ncol=3)
    ax = axes[1]
    sw = scores.dropna(subset=["switch_per_100m"]).drop_duplicates(["metode", "target_sw"])
    names = [f"{r.metode}\n({r.target_sw})" if r.target_sw else r.metode for r in sw.itertuples()]
    cols = [C_LOG if r.metode.startswith("Log") else C_HMM if r.metode.startswith("HMM") else
            C_SM if "halus" in r.metode else C_RAW for r in sw.itertuples()]
    yy = np.arange(len(sw))
    ax.barh(yy, sw.switch_per_100m, color=cols, height=0.6)
    for y_, v in zip(yy, sw.switch_per_100m):
        ax.text(v + 0.3, y_, f"{v:.1f}", va="center", fontsize=7.5)
    ax.set_yticks(yy, names, fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("Pergantian label per 100 m", fontsize=8.5)
    ax.set_title("Fragmentasi (log sebagai acuan)", fontsize=9.5)
    ax = axes[2]
    for m, col, ls in (("Log alterasi", C_LOG, "-"), ("RF dihaluskan (alterasi)", C_SM, "--"), ("HMM (ML-4)", C_HMM, "-")):
        t = tw[tw.label.eq(m)]
        mid = (t.d_from + t.d_to) / 2
        ax.plot(mid, t.agree, ls, marker="o", ms=5, color=col, lw=1.6, label=m)
        ax.axhline(t.chance.iloc[0], color=col, lw=0.8, ls=":")
    ax.set_xlabel("Jarak 3D antar komposit lubang berbeda (m)", fontsize=8.5)
    ax.set_ylabel("Proporsi pasangan berlabel sama", fontsize=8.5)
    ax.set_ylim(0, 1)
    ax.set_title("Pad kembar 005/014, 010/011, 016/017\n(garis titik = peluang kebetulan Σp²)", fontsize=9.5)
    ax.legend(fontsize=7.5, frameon=False)
    for a_ in axes:
        a_.spines[["top", "right"]].set_visible(False)
        a_.tick_params(labelsize=8)
    fig.suptitle("Pembanding §9.2: PCA → Random Forest + penghalusan ke bawah lubang vs HMM (komposit 1 m)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main():
    m11 = load_script("11_ml4_hmm.py")
    c, collar, summ, _ = m11.load()
    ok = c.comp_ok.to_numpy(bool)
    seg_all = gs.segments(c.SiteID.to_numpy(), ok)
    rows = np.flatnonzero(ok)
    seg = seg_all[rows]
    site = c.SiteID.to_numpy()[rows]
    pads = c.SiteID.map(classify.pad_groups(collar)).to_numpy()[rows]
    V, cens, dl = m11.matrices(c, rows, m11.FEATS, summ)
    L = gs.log_features(V, cens, dl, np.random.default_rng(SEED))   # draw 0 of the ML-4 pipeline
    c_ok = c.loc[rows].reset_index(drop=True)
    hmm = pd.read_csv(paths.PROCESSED / "ml" / "komposit__ml4_hmm.csv")
    k = c_ok[["SiteID", "DepthFrom"]].rename(columns={"SiteID": "HoleID", "DepthFrom": "From"})
    state = k.merge(hmm[["HoleID", "From", "ML_hmm_status"]], on=["HoleID", "From"], how="left").ML_hmm_status
    assert state.notna().all(), "HMM state missing on a comp_ok composite"
    state = state.astype(int).to_numpy()
    xyz = c_ok[["X_mid", "Y_mid", "Z_mid"]].to_numpy()
    print(f"composites {len(rows)}, pads {len(np.unique(pads))}, segments {len(np.unique(seg))}")

    out_ml = pd.DataFrame({"HoleID": c.SiteID, "From": c.DepthFrom})
    score_rows, fold_rows, tw_parts = [], [], []
    for tgt, (col, classes) in TARGETS.items():
        y = c_ok[col].where(c_ok[col].isin(classes)).to_numpy(object)
        res = Parallel(n_jobs=-1)(delayed(outer_fold)(p, L, y, pads, seg, classes) for p in sorted(np.unique(pads)))
        P_raw = np.full((len(rows), len(classes)), np.nan)
        P_sm = P_raw.copy()
        for pad, te, P, Ps, leaf, w, crit in res:
            P_raw[te], P_sm[te] = P, Ps
            yt = y[te]
            m = pd.notna(yt)
            fold_rows.append({"target": tgt, "pad": pad, "n": int(len(te)), "n_label": int(m.sum()), "leaf": leaf,
                              "w_m": w, **{f"{c_}_w{k_}": v[c_] for k_, v in crit.items() for c_ in v},
                              "bal_acc_mentah": classify.scores(yt[m], P[m], classes)["bal_acc"] if m.any() else np.nan,
                              "bal_acc_halus": classify.scores(yt[m], Ps[m], classes)["bal_acc"] if m.any() else np.nan})
        assert not np.isnan(P_raw).any()
        lab_raw, lab_sm = classify.predict(P_raw, classes), classify.predict(P_sm, classes)
        m = pd.notna(y)
        for name, lab, P in (("RF mentah", lab_raw, P_raw), ("RF dihaluskan", lab_sm, P_sm)):
            s = classify.scores(y[m], P[m], classes)
            score_rows.append({"target": tgt, "metode": name, "bal_acc": s["bal_acc"], "kappa": s["kappa"],
                               "logloss": loss(y, P, classes), **agreement(y, lab),
                               "switch_per_100m": gs.switch_rate(lab, seg), "target_sw": tgt})
        score_rows.append({"target": tgt, "metode": "HMM (ML-4)", **agreement(y, state),
                           "switch_per_100m": gs.switch_rate(state, seg), "target_sw": ""})
        score_rows.append({"target": tgt, "metode": f"Log {tgt}", "switch_per_100m": gs.switch_rate(y, seg),
                           "target_sw": ""})
        short = "alt" if tgt == "alterasi" else "oks"
        full = np.full(len(c), None, object)
        full[rows] = lab_sm
        out_ml[f"ML_s9_rf_{short}"] = full
        pm = np.full(len(c), np.nan)
        pm[rows] = P_sm.max(1).round(4)
        out_ml[f"ML_s9_rf_{short}_p_maks"] = pm
        if tgt == "alterasi":
            tw_parts.append(twins(xyz, lab_sm, site, pads).assign(label="RF dihaluskan (alterasi)"))
            tw_parts.append(twins(xyz, np.where(pd.notna(y), y, "NA"), site, pads).assign(label="Log alterasi"))
    tw_parts.append(twins(xyz, state, site, pads).assign(label="HMM (ML-4)"))
    scores = pd.DataFrame(score_rows)
    folds = pd.DataFrame(fold_rows)
    tw = pd.concat(tw_parts, ignore_index=True)
    P_ = paths.PROCESSED
    scores.round(4).to_csv(P_ / "s9_rf_smoother_scores.csv", index=False)
    folds.round(4).to_csv(P_ / "s9_rf_smoother_folds.csv", index=False)
    tw.round(4).to_csv(P_ / "s9_rf_smoother_kembar.csv", index=False)
    assert not out_ml.duplicated(["HoleID", "From"]).any()
    out_ml.to_csv(P_ / "ml" / "komposit__s9_rf.csv", index=False)
    fig(scores, tw, paths.FIGURES / "14_rf_vs_hmm_v1.png")
    print(scores.round(3).to_string(index=False))
    print(folds.groupby("target")[["leaf", "w_m"]].agg(lambda v: v.value_counts().to_dict()).to_string())
    print(tw.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
