"""ML-4: downhole geochem-stratigraphy by Gaussian HMM (AGENTS.md §6 task 4). Plan: LOG.md,
2026-11-03 ML-4 entry.

One full-covariance Gaussian HMM across all 19 holes on 1 m composites (log10 Au, Ag, Cu, As;
censored values spread over [DL/3, DL], others dequantised; median/MAD scaled). K 2–8 chosen by
leave-one-pad-out held-out log-likelihood; a GMM with the same emissions is the no-sequence
comparator. Posteriors averaged over dequantisation draws; pad bootstrap for stability and
intervals; sensitivities (no Ag, +SCIS, +CuCN/Cu, K ± 1, long-sample repeats collapsed);
comparison with logs and ML-2; cross-hole agreement by 3D distance.
Reads data/interim/06_composites.csv, 05_assay_joined.csv, 03_collar.csv, 01_element_summary.csv,
data/processed/element_thresholds.csv, data/processed/ml/assay__ml2_classify.csv; writes
data/processed/ml/komposit__ml4_hmm.csv, data/processed/ml4_{summary,states,comparisons}.csv,
gis/ml4_hmm.gpkg, outputs/figures/11_*_v1.png. Prints summaries only.
Run: uv run python scripts/11_ml4_hmm.py  (then scripts/12_ml4_sections.py, scripts/07_export.py)
"""
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio
import shapely
from joblib import Parallel, delayed
from matplotlib.patches import Patch
from sklearn.metrics import adjusted_rand_score

from src import classify, geostrat as gs, paths, zonation as zn

SEED = 0
FEATS = ["AuPPM", "AgPPM", "CuPPM", "AsPPM"]
K_GRID = range(2, 9)
N_DRAWS = 20          # dequantisation / censoring draws (posterior average)
N_DRAWS_CV = 5
RESTARTS = 10
RESTARTS_CV = 5
RESTARTS_BOOT = 3
N_BOOT = 100
MIN_STATE_N = 30      # admissible: every state holds ≥ 30 composites (Σ posterior) ...
MIN_STATE_HOLES = 2   # ... and is the most probable state in ≥ 2 holes
CENS_SHARE = 0.5      # a composite is censored for an element when ≥ half its length is
P_AMBIG = 0.5
FLOOR_LOG10 = 0.05    # ML-1 variance floor, in log10
EDGES = np.arange(0, 101, 10)
TWIN_EDGES = np.array([0, 10, 20, 50, 100])

OX_ID = {"Oxide": "Oksida", "Transition": "Transisi", "Sulphide": "Sulfida"}
ALT_ID = {"AA": "Argilik lanjut", "SI": "Silika", "AR": "Argilik", "PP": "Propilitik", "UA": "Tanpa alterasi"}
C_INK, C_INK2, C_NULL = "#0b0b0b", "#52514e", "#b9b8b2"
ALT_COL = {"SI": "#7b3294", "AA": "#c2a5cf", "AR": "#a6dba0", "PP": "#008837", "UA": "#e0e0e0"}
OX_COL = {"Oxide": "#d7301f", "Transition": "#fdbb84", "Sulphide": "#525252"}

DL_HARMONISED = {"AuPPM", "AgPPM"}   # others have job-specific DLs: DL = 2 × the censored value


def el(c: str) -> str:
    return c.removesuffix("PPM").removesuffix("_PCT")


# --- data ---------------------------------------------------------------------------
def load():
    c = pd.read_csv(paths.INTERIM / "06_composites.csv", low_memory=False)
    c = c.sort_values(["SiteID", "DepthFrom"]).reset_index(drop=True)
    collar = pd.read_csv(paths.INTERIM / "03_collar.csv")
    summ = pd.read_csv(paths.INTERIM / "01_element_summary.csv")
    thr = pd.read_csv(paths.PROCESSED / "element_thresholds.csv")
    return c, collar, summ, thr


def matrices(c: pd.DataFrame, rows: np.ndarray, feats: list[str], summ: pd.DataFrame):
    """Values, censored mask and per-cell DL for `feats` on `rows`."""
    V = c.loc[rows, [f"{f}_ml" for f in feats]].to_numpy(float)
    cens = np.column_stack([c.loc[rows, f"{f}_cens_frac"].fillna(0).to_numpy() >= CENS_SHARE
                            if f"{f}_cens_frac" in c else np.zeros(len(rows), bool) for f in feats])
    dl = 2 * V
    for j, f in enumerate(feats):
        if f in DL_HARMONISED:
            h = float(summ.loc[summ.dataset.eq("assay") & summ.column.eq(f), "harmonised_dl"].iloc[0])
            assert np.isclose(np.nanmin(V[:, j]), h / 2), f"{f}: floor is not DL/2"
            dl[:, j] = h
    return V, cens, dl


def draws(V, cens, dl, n: int, seed: int = SEED) -> list[np.ndarray]:
    return [gs.log_features(V, cens, dl, np.random.default_rng(seed + d)) for d in range(n)]


# --- fitting jobs -------------------------------------------------------------------
def cv_job(k, pad, d, X, seg, pads, min_covar):
    tr, te = pads != pad, pads == pad
    m = gs.fit_hmm(X[tr], gs.lengths(seg[tr]), k, min_covar, RESTARTS_CV, SEED)
    g = gs.fit_gmm(X[tr], k, min_covar, RESTARTS_CV, SEED)
    n = int(te.sum())
    return {"K": k, "pad": pad, "draw": d, "n_test": n,
            "ll_hmm": m.score(X[te], gs.lengths(seg[te])) / n, "ll_gmm": g.score(X[te])}


def boot_job(b, X0, seg, pads, ref_means, k, min_covar):
    rng = np.random.default_rng(SEED + 1000 + b)
    pick = rng.choice(np.unique(pads), size=len(np.unique(pads)), replace=True)
    idx = np.concatenate([np.flatnonzero(pads == p) for p in pick])
    # a duplicated pad repeats its segments: renumber so each copy is its own sequence
    copy = np.concatenate([np.full((pads == p).sum(), i) for i, p in enumerate(pick)])
    sb = seg[idx] + copy * (seg.max() + 1)
    m = gs.fit_hmm(X0[idx], gs.lengths(sb), k, min_covar, RESTARTS_BOOT, SEED + b)
    perm = gs.align(ref_means, m.means_)
    P = m.predict_proba(X0, gs.lengths(seg))[:, perm]
    return {"lab": P.argmax(1) + 1, "means": m.means_[perm], "trans": m.transmat_[np.ix_(perm, perm)]}


def ordered_fit(X, lens, k, min_covar, restarts=RESTARTS):
    m = gs.fit_hmm(X, lens, k, min_covar, restarts, SEED)
    return m, gs.order(m.means_)


def posterior(m, o, Xs, lens) -> np.ndarray:
    P = np.mean([m.predict_proba(X, lens) for X in Xs], axis=0)[:, o]
    assert np.allclose(P.sum(1), 1)
    return P


# --- comparisons --------------------------------------------------------------------
def nearest_assay_labels(c: pd.DataFrame, ok_rows: np.ndarray) -> pd.DataFrame:
    """ML-2 predictions and NAG pH of the longest assay whose midpoint lies in each composite."""
    a = pd.read_csv(paths.INTERIM / "05_assay_joined.csv", usecols=["SampleID", "SiteID", "DepthFrom", "DepthTo",
                                                                   "NAGpH_ml"], low_memory=False)
    ml2 = pd.read_csv(paths.PROCESSED / "ml" / "assay__ml2_classify.csv",
                      usecols=["SampleID", "ML_alt_prediksi", "ML_oks_prediksi"])
    a = a.merge(ml2, on="SampleID", how="left")
    a["From"] = np.floor((a.DepthFrom + a.DepthTo) / 2)
    a["len"] = a.DepthTo - a.DepthFrom
    a = a.sort_values("len", ascending=False).drop_duplicates(["SiteID", "From"])
    k = c.loc[ok_rows, ["SiteID", "DepthFrom"]].rename(columns={"DepthFrom": "From"})
    out = k.merge(a[["SiteID", "From", "ML_alt_prediksi", "ML_oks_prediksi", "NAGpH_ml"]], on=["SiteID", "From"],
                  how="left")
    assert len(out) == len(k)
    return out.drop(columns=["SiteID", "From"]).reset_index(drop=True)


def log_vs(state, logged) -> dict:
    s = pd.Series(logged).reset_index(drop=True)
    keep = s.notna().to_numpy()
    st = np.asarray(state)[keep]
    return {"n": int(keep.sum()), "cramers_v": zn.cramers_v(st, s[keep]),
            "ari": adjusted_rand_score(st, s[keep].astype(str))}


# --- figures ------------------------------------------------------------------------
def clean_axes(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def fig_k(cvsum: pd.DataFrame, k_sel: int, path):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    ax = axes[0]
    for col, lab, colour, mk in (("hmm", "HMM (dengan transisi)", C_INK, "o"), ("gmm", "GMM (tanpa transisi)", C_INK2, "s")):
        ax.errorbar(cvsum.K, cvsum[f"ll_{col}"], yerr=cvsum[f"se_{col}"], marker=mk, ms=5, lw=1.5, capsize=3,
                    color=colour, label=lab, ls="-" if col == "hmm" else (0, (4, 2)))
    ax.axvline(k_sel, color=C_NULL, lw=6, alpha=0.5, zorder=0)
    ax.set_xlabel("Jumlah status K", fontsize=8.5)
    ax.set_ylabel("Log-likelihood uji per komposit", fontsize=8.5)
    ax.set_title("Validasi silang tinggalkan-satu-pad (12 pad)", fontsize=9.5)
    ax.legend(fontsize=7.5, frameon=False)
    ax = axes[1]
    ax.plot(cvsum.K, cvsum.bic - cvsum.bic.min(), "o-", color=C_INK, ms=5)
    ax.axvline(k_sel, color=C_NULL, lw=6, alpha=0.5, zorder=0)
    ax.set_xlabel("Jumlah status K", fontsize=8.5)
    ax.set_ylabel("ΔBIC (HMM, semua data)", fontsize=8.5)
    ax.set_title("BIC (ditampilkan saja; autokorelasi 1 m)", fontsize=9.5)
    for a in axes:
        clean_axes(a)
        a.set_xticks(list(K_GRID))
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_profiles(c_ok: pd.DataFrame, state: np.ndarray, names: list[str], cols, path):
    k = len(names)
    fig, axes = plt.subplots(1, 4, figsize=(11, 3.6), sharey=True)
    for ax, f in zip(axes, FEATS):
        data = [c_ok.loc[state == s, f"{f}_ml"].to_numpy() for s in range(1, k + 1)]
        bp = ax.boxplot(data, vert=False, patch_artist=True, widths=0.6, showfliers=False, whis=(5, 95),
                        medianprops=dict(color=C_INK, lw=1.4), whiskerprops=dict(color=C_INK2),
                        capprops=dict(color=C_INK2), boxprops=dict(edgecolor=C_INK2))
        for p, col in zip(bp["boxes"], cols):
            p.set_facecolor(col)
        ax.set_xscale("log")
        ax.set_xlabel(f"{el(f)} (ppm, skala log)", fontsize=8.5)
        clean_axes(ax)
    axes[0].set_yticks(range(1, k + 1), names, fontsize=7.5)
    fig.suptitle("Kimia tiap status HMM (komposit 1 m; kotak = kuartil, garis = persentil 5–95)", fontsize=9.5)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_transitions(T, run_m, run_ci, names, path):
    k = len(names)
    fig, ax = plt.subplots(figsize=(1.1 * k + 3, 0.8 * k + 1.5))
    im = ax.imshow(T, cmap="Greys", vmin=0, vmax=1)
    for i in range(k):
        for j in range(k):
            ax.text(j, i, f"{T[i, j]:.2f}", ha="center", va="center", fontsize=7.5,
                    color="white" if T[i, j] > 0.5 else C_INK)
    lab = [f"{n}\n(≈ {r:.0f} m; {lo:.0f}–{hi:.0f})" for n, r, (lo, hi) in zip(names, run_m, run_ci)]
    ax.set_yticks(range(k), lab, fontsize=7)
    ax.set_xticks(range(k), [n.split(" ")[0] for n in names], fontsize=7.5)
    ax.set_xlabel("Status pada meter berikutnya", fontsize=8.5)
    ax.set_ylabel("Status sekarang (rata-rata tebal tinggal, 5–95% bootstrap)", fontsize=8)
    ax.set_title("Peluang transisi antar status per meter", fontsize=9.5)
    fig.colorbar(im, ax=ax, fraction=0.04, label="Peluang")
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_strips(c: pd.DataFrame, cols, names, path):
    holes = sorted(c.SiteID.unique())
    depth = c.groupby("SiteID").DepthTo.max()
    fig, axes = plt.subplots(1, len(holes), figsize=(16, 7.5), sharey=True)
    for ax, h in zip(axes, holes):
        g = c[c.SiteID.eq(h)]
        for x0, colmap, key in ((0, None, "ML_hmm_status"), (1, ALT_COL, "AltFacies"), (2, OX_COL, "ox_state")):
            for r in g.itertuples():
                v = getattr(r, key)
                if pd.isna(v):
                    colr = "white"
                elif colmap is None:
                    colr = cols[int(v) - 1]
                else:
                    colr = colmap.get(v, "white")
                ax.add_patch(plt.Rectangle((x0, r.DepthFrom), 0.92, r.DepthTo - r.DepthFrom, color=colr, lw=0))
            if colmap is None:   # state number on runs ≥ 8 m (secondary encoding), ambiguous hatched
                gs_ = g[g.ML_hmm_status.notna()]
                seg_h = np.cumsum(np.r_[True, np.diff(gs_.DepthFrom.to_numpy()) > 1])
                mark = gs.run_label_rows(gs_.ML_hmm_status.astype(int).to_numpy(), seg_h, 8)
                for r in gs_[mark].itertuples():
                    v = int(r.ML_hmm_status)
                    ax.text(x0 + 0.46, r.DepthFrom + 0.5, str(v), ha="center", va="center", fontsize=4.5,
                            color="white" if v in (1, 5) else C_INK)
                for r in g[g.ML_hmm_ambigu.eq("Y")].itertuples():
                    ax.add_patch(plt.Rectangle((x0, r.DepthFrom), 0.92, 1, fill=False, hatch="////", lw=0,
                                               edgecolor="white"))
        ax.set_xlim(0, 3)
        ax.set_xticks([0.46, 1.46, 2.46], ["HMM", "Alt", "Oks"], fontsize=6, rotation=90)
        ax.set_title(h.replace("RJDH", "DH"), fontsize=7.5)
        ax.set_ylim(depth.max() + 2, 0)
        for s in ("top", "right", "bottom"):
            ax.spines[s].set_visible(False)
        ax.tick_params(axis="x", length=0)
    axes[0].set_ylabel("Kedalaman sepanjang lubang (m)", fontsize=8.5)
    handles = ([Patch(color=col, label=n) for col, n in zip(cols, names)]
               + [Patch(facecolor="white", hatch="////", edgecolor=C_INK2, label="Ambigu (p < 0,5)")]
               + [Patch(color=ALT_COL[a], label=f"Alterasi: {ALT_ID[a]}") for a in ALT_COL]
               + [Patch(color=OX_COL[o], label=f"Oksidasi: {OX_ID[o]}") for o in OX_COL])
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=7, frameon=False, bbox_to_anchor=(0.5, -0.08))
    fig.suptitle("Status HMM dibandingkan dengan alterasi dan oksidasi hasil logging, 19 lubang bor", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_continuity(cont: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    style = {"HMM": (C_INK, "o", "-"), "GMM": (C_INK2, "s", (0, (4, 2))), "Alterasi (log)": ("#7b3294", "^", "-")}
    for name, g in cont[cont.scope.eq("semua")].groupby("label", sort=False):
        col, mk, ls = style[name]
        x = (g.d_from + g.d_to) / 2
        ax.plot(x, g.agree, marker=mk, color=col, ls=ls, lw=1.5, ms=5, label=f"{name}")
        ax.axhline(g.chance.iloc[0], color=col, lw=0.9, ls=":", alpha=0.8)
    ax.set_xlabel("Jarak 3D antar komposit dari lubang berbeda (m)", fontsize=8.5)
    ax.set_ylabel("Proporsi pasangan berstatus sama", fontsize=8.5)
    ax.set_title("Kesinambungan antar lubang (garis titik = peluang acak)", fontsize=9.5)
    ax.legend(fontsize=7.5, frameon=False)
    clean_axes(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


# --- main ---------------------------------------------------------------------------
def main():
    c, collar, summ, thr = load()
    ok = c.comp_ok.to_numpy(bool)
    seg_all = gs.segments(c.SiteID.to_numpy(), ok)
    rows = np.flatnonzero(ok)
    seg = seg_all[rows]
    lens = gs.lengths(seg)
    site = c.SiteID.to_numpy()[rows]
    pads = c.SiteID.map(classify.pad_groups(collar)).to_numpy()[rows]
    print(f"composites ok {len(rows)}, segments {len(lens)} (min {lens.min()}, median {int(np.median(lens))}), "
          f"pads {len(np.unique(pads))}")

    V, cens, dl = matrices(c, rows, FEATS, summ)
    print("censored share:", dict(zip([el(f) for f in FEATS], cens.mean(0).round(3))))
    Ls = draws(V, cens, dl, N_DRAWS)
    med, mad = zn.robust_params(Ls[0])
    Xs = [(L - med) / mad for L in Ls]
    min_covar = float((FLOOR_LOG10 / np.median(mad)) ** 2)
    print(f"MAD (log10) {dict(zip([el(f) for f in FEATS], mad.round(3)))}; min_covar {min_covar:.4f}")

    # --- K selection ----------------------------------------------------------------
    jobs = [(k, p, d) for k in K_GRID for p in np.unique(pads) for d in range(N_DRAWS_CV)]
    cv = pd.DataFrame(Parallel(n_jobs=-1)(delayed(cv_job)(k, p, d, Xs[d], seg, pads, min_covar) for k, p, d in jobs))
    per_pad = cv.groupby(["K", "pad"])[["ll_hmm", "ll_gmm"]].mean().reset_index()
    full = dict(zip(K_GRID, Parallel(n_jobs=-1)(delayed(ordered_fit)(Xs[0], lens, k, min_covar) for k in K_GRID)))
    rows_k = []
    for k in K_GRID:
        g = per_pad[per_pad.K.eq(k)]
        m, o = full[k]
        cnt, nh = gs.occupancy(m.predict_proba(Xs[0], lens), site)
        rows_k.append({"K": k, "ll_hmm": g.ll_hmm.mean(), "se_hmm": g.ll_hmm.std(ddof=1) / np.sqrt(len(g)),
                       "ll_gmm": g.ll_gmm.mean(), "se_gmm": g.ll_gmm.std(ddof=1) / np.sqrt(len(g)),
                       "hmm_minus_gmm": (g.ll_hmm - g.ll_gmm).mean(), "bic": m.bic(Xs[0], lens),
                       "min_state_n": cnt.min(), "min_state_holes": int(nh.min()),
                       "admissible": bool(cnt.min() >= MIN_STATE_N and nh.min() >= MIN_STATE_HOLES)})
    cvsum = pd.DataFrame(rows_k)
    best = cvsum.loc[cvsum.ll_hmm.idxmax()]
    cand = cvsum[(cvsum.ll_hmm >= best.ll_hmm - best.se_hmm) & cvsum.admissible]
    assert len(cand), "no admissible K within 1 SE of the best: stop and report"
    K = int(cand.K.min())
    cvsum["selected"] = cvsum.K.eq(K)
    print("K selection (held-out LL per composite ± SE):")
    print(cvsum.round(4).to_string(index=False))
    print(f"-> K = {K} (best K {int(best.K)})")
    assert set(cv.groupby(["K", "pad", "draw"]).size()) == {1}

    # --- main model -----------------------------------------------------------------
    m, o = full[K]
    P = posterior(m, o, Xs, lens)
    state = P.argmax(1) + 1
    inv = np.empty(K, int)
    inv[o] = np.arange(K)
    vit = inv[m.predict(Xs[0], lens)] + 1
    means_log = m.means_[o] * mad + med
    assert np.all(np.diff(means_log[:, 0]) > 0), "states not ordered by Au"
    T = m.transmat_[np.ix_(o, o)]
    g = gs.fit_gmm(Xs[0], K, min_covar, RESTARTS, SEED)
    og = gs.order(g.means_)
    ginv = np.empty(K, int)
    ginv[og] = np.arange(K)
    gmm_lab = ginv[g.predict(Xs[0])] + 1

    # --- bootstrap ------------------------------------------------------------------
    boot = Parallel(n_jobs=-1)(delayed(boot_job)(b, Xs[0], seg, pads, m.means_[o], K, min_covar)
                               for b in range(N_BOOT))
    B_lab = np.array([b["lab"] for b in boot])
    stab = zn.stability(state, B_lab)
    ari_b = zn.boot_ari(state, B_lab)
    B_means = np.array([b["means"] * mad + med for b in boot])        # log10
    B_run = np.array([gs.run_length(b["trans"]) for b in boot])
    B_diag = np.array([np.diag(b["trans"]) for b in boot])
    print(f"bootstrap ARI median {np.median(ari_b):.2f} (5–95% {np.percentile(ari_b, 5):.2f}–"
          f"{np.percentile(ari_b, 95):.2f}); stability median {np.median(stab):.2f}")

    # --- names ------------------------------------------------------------------------
    t = thr[thr.dataset.eq("bor")].set_index("element")
    au_t = (t.loc["Au", "T1"], t.loc["Au", "T2"])
    cu_t = t.loc["Cu", "T1"]
    c_ok = c.loc[rows].reset_index(drop=True)
    names, desc = [], []
    for s in range(1, K + 1):
        sel = state == s
        au, cu = c_ok.loc[sel, "AuPPM_ml"].median(), c_ok.loc[sel, "CuPPM_ml"].median()
        au_c = "Au rendah" if au < au_t[0] else ("Au sedang" if au < au_t[1] else "Au tinggi")
        cu_c = "Cu tinggi" if cu >= cu_t else "Cu rendah"
        oxm = c_ok.loc[sel, "ox_state"].mode()
        oxs = OX_ID[oxm.iloc[0]] if len(oxm) else "?"
        names.append(f"S{s} {au_c}, {cu_c} ({oxs})")
        desc.append((au_c, cu_c, oxs))
    print("states:", names)

    # --- sensitivities ------------------------------------------------------------------
    sens = []

    def subseq(mask):
        """Segments of a row subset: a dropped row inside a segment breaks the sequence."""
        idx = np.flatnonzero(mask)
        new_seg = np.r_[True, (seg[idx][1:] != seg[idx][:-1]) | (np.diff(idx) > 1)]
        return np.cumsum(new_seg) - 1

    def refit_compare(label, mask, feats=None, mats=None, k=K):
        Vx, cx, dx = matrices(c, rows[mask], feats, summ) if mats is None else mats
        sg = subseq(mask)
        L = draws(Vx, cx, dx, 5)
        mm, mmad = zn.robust_params(L[0])
        X = [(x - mm) / mmad for x in L]
        mk, ok_ = ordered_fit(X[0], gs.lengths(sg), k, min_covar, 5)
        lab = posterior(mk, ok_, X, gs.lengths(sg)).argmax(1) + 1
        sens.append({"sensitivity": label, "n": int(mask.sum()), "K": k,
                     "ari_vs_main": adjusted_rand_score(state[mask], lab),
                     "v_ox_main": log_vs(state[mask], c_ok.ox_state[mask])["cramers_v"],
                     "v_ox_sens": log_vs(lab, c_ok.ox_state[mask])["cramers_v"],
                     "v_alt_main": log_vs(state[mask], c_ok.AltFacies[mask])["cramers_v"],
                     "v_alt_sens": log_vs(lab, c_ok.AltFacies[mask])["cramers_v"],
                     "switch_main": gs.switch_rate(state[mask], sg), "switch_sens": gs.switch_rate(lab, sg)})
        return lab

    allrows = np.ones(len(rows), bool)
    refit_compare("tanpa Ag", allrows, ["AuPPM", "CuPPM", "AsPPM"])
    scis = (c_ok.S_method_c.eq("SCIS") & c_ok.SCIS_PCT_ml.notna()).to_numpy()
    lab_s = refit_compare("+ S (SCIS), 16 lubang", scis, FEATS + ["SCIS_PCT"])
    # log CuCN/Cu as an extra column: ratio values are not censored, so no spreading
    cucn = (c_ok.CuCN_ratio > 0).to_numpy()
    Vc, cc, dc = matrices(c, rows[cucn], FEATS, summ)
    Vc = np.column_stack([Vc, c_ok.CuCN_ratio[cucn].to_numpy()])
    cc = np.column_stack([cc, np.zeros(cucn.sum(), bool)])
    dc = np.column_stack([dc, np.ones(cucn.sum())])
    refit_compare("+ CuCN/Cu", cucn, mats=(Vc, cc, dc))
    for k in (K - 1, K + 1):
        lab = posterior(*full[k], Xs, lens).argmax(1) + 1
        sens.append({"sensitivity": f"K = {k}", "n": len(rows), "K": k,
                     "ari_vs_main": adjusted_rand_score(state, lab),
                     "v_ox_main": log_vs(state, c_ok.ox_state)["cramers_v"], "v_ox_sens": log_vs(lab, c_ok.ox_state)["cramers_v"],
                     "v_alt_main": log_vs(state, c_ok.AltFacies)["cramers_v"],
                     "v_alt_sens": log_vs(lab, c_ok.AltFacies)["cramers_v"],
                     "switch_main": gs.switch_rate(state, seg), "switch_sens": gs.switch_rate(lab, seg)})
    # long-sample repeats collapsed: one observation per source sample
    keep = gs.collapse_repeats(V, seg, c_ok.comp_shared_src.to_numpy(bool))
    mc = gs.fit_hmm(Xs[0][keep], gs.lengths(seg[keep]), K, min_covar, 5, SEED)
    perm = gs.align(m.means_[o], mc.means_)
    Tc = mc.transmat_[np.ix_(perm, perm)]
    lab_c = mc.predict_proba(Xs[0], lens)[:, perm].argmax(1) + 1
    sens.append({"sensitivity": "ulangan sampel panjang digabung", "n": int(keep.sum()), "K": K,
                 "ari_vs_main": adjusted_rand_score(state, lab_c),
                 "switch_main": gs.switch_rate(state, seg), "switch_sens": gs.switch_rate(lab_c, seg),
                 "run_m_main": " ".join(f"{x:.1f}" for x in gs.run_length(T)),
                 "run_m_sens": " ".join(f"{x:.1f}" for x in gs.run_length(Tc))})
    sens = pd.DataFrame(sens)
    print("sensitivities:")
    print(sens.round(3).to_string(index=False))

    # --- comparisons -------------------------------------------------------------------
    ext = nearest_assay_labels(c, rows)
    comp_rows = []
    for name, lab in (("HMM", state), ("GMM", gmm_lab), ("HMM Viterbi", vit)):
        for logn, logged in (("alterasi", c_ok.AltFacies), ("oksidasi", c_ok.ox_state), ("litologi", c_ok.Lith_group),
                             ("ML-2 alterasi", ext.ML_alt_prediksi), ("ML-2 oksidasi", ext.ML_oks_prediksi)):
            comp_rows.append({"kind": "vs_log", "label": name, "against": logn, **log_vs(lab, logged)})
    comp_rows.append({"kind": "vs_log", "label": "HMM", "against": "GMM", "n": len(rows),
                      "ari": adjusted_rand_score(state, gmm_lab)})
    sw = {"HMM": gs.switch_rate(state, seg), "HMM Viterbi": gs.switch_rate(vit, seg), "GMM": gs.switch_rate(gmm_lab, seg),
          "log alterasi": gs.switch_rate(c_ok.AltFacies, seg), "log oksidasi": gs.switch_rate(c_ok.ox_state, seg),
          "log litologi": gs.switch_rate(c_ok.Lith_group, seg)}
    for k_, v in sw.items():
        comp_rows.append({"kind": "switch_per_100m", "label": k_, "value": v})
    for logn, logged in (("alterasi", c_ok.AltFacies), ("oksidasi", c_ok.ox_state), ("litologi", c_ok.Lith_group)):
        ct = pd.crosstab(pd.Series(state, name="state"), logged.reset_index(drop=True))
        for s_, r_ in ct.iterrows():
            for cat, n_ in r_.items():
                comp_rows.append({"kind": "crosstab", "label": f"S{s_}", "against": f"{logn}:{cat}", "n": int(n_)})
    xyz = c_ok[["X_mid", "Y_mid", "Z_mid"]].to_numpy()
    cont = []
    for name, lab in (("HMM", state), ("GMM", gmm_lab), ("Alterasi (log)", c_ok.AltFacies.fillna("NA").to_numpy())):
        t_ = gs.pair_agreement(xyz, np.asarray(lab).astype(str), site, EDGES)
        cont.append(t_.assign(label=name, scope="semua"))
        twins = [p for p in np.unique(pads) if (pd.Series(site[pads == p]).nunique() > 1)]
        tw = pd.concat([gs.pair_agreement(xyz[pads == p], np.asarray(lab).astype(str)[pads == p], site[pads == p],
                                          TWIN_EDGES).assign(pad=p) for p in twins])
        tw_pool = tw.groupby(["d_from", "d_to"]).apply(
            lambda x: pd.Series({"n_pairs": x.n_pairs.sum(),
                                 "agree": np.average(x.agree.fillna(0), weights=x.n_pairs) if x.n_pairs.sum() else np.nan,
                                 "chance": t_.chance.iloc[0]}), include_groups=False).reset_index()
        cont.append(tw_pool.assign(label=name, scope="pad kembar"))
    cont = pd.concat(cont, ignore_index=True)
    print("switches per 100 m:", {k_: round(v, 2) for k_, v in sw.items()})
    print("cross-hole agreement:")
    print(cont.pivot_table(index=["scope", "d_from"], columns="label", values="agree").round(2).to_string())
    print(cont.groupby(["scope", "label"]).chance.first().round(2).to_dict())

    # --- state table ---------------------------------------------------------------------
    st_rows = []
    run = gs.run_length(T)
    for s in range(1, K + 1):
        sel = state == s
        r = {"state": s, "nama": names[s - 1], "n": int(sel.sum()), "n_holes": int(len(np.unique(site[sel]))),
             "holes": " ".join(sorted(h.replace("RJDH", "") for h in np.unique(site[sel]))),
             "p_maks_median": float(np.median(P[sel].max(1))), "stability_median": float(np.median(stab[sel])),
             "stay_prob": T[s - 1, s - 1], "stay_ci05": np.percentile(B_diag[:, s - 1], 5),
             "stay_ci95": np.percentile(B_diag[:, s - 1], 95), "run_m": run[s - 1],
             "run_ci05": np.percentile(B_run[:, s - 1], 5), "run_ci95": np.percentile(B_run[:, s - 1], 95)}
        for j, f in enumerate(FEATS):
            r[f"{el(f)}_gmean"] = 10 ** means_log[s - 1, j]
            r[f"{el(f)}_gmean_ci05"] = 10 ** np.percentile(B_means[:, s - 1, j], 5)
            r[f"{el(f)}_gmean_ci95"] = 10 ** np.percentile(B_means[:, s - 1, j], 95)
            r[f"{el(f)}_median"] = c_ok.loc[sel, f"{f}_ml"].median()
        for col in ("SCIS_PCT_ml", "AuCN_ratio", "CuCN_ratio"):
            v = c_ok.loc[sel, col]
            r[f"{col}_median"], r[f"{col}_n"] = v.median(), int(v.notna().sum())
        nag = ext.NAGpH_ml[sel].dropna()
        r["NAGpH_n"], r["NAGpH_median"] = len(nag), nag.median() if len(nag) else np.nan
        r["NAGpH_lt45_share"] = float((nag < 4.5).mean()) if len(nag) else np.nan
        for logn, col in (("alt", "AltFacies"), ("ox", "ox_state"), ("lith", "Lith_group")):
            vc = c_ok.loc[sel, col].value_counts(normalize=True)
            r[f"{logn}_mode"], r[f"{logn}_mode_share"] = (vc.index[0], vc.iloc[0]) if len(vc) else ("", np.nan)
        for j in range(K):
            r[f"to_S{j + 1}"] = T[s - 1, j]
        st_rows.append(r)
    states = pd.DataFrame(st_rows)
    states["warna"] = gs.state_colours(K)
    print(states[["state", "nama", "n", "n_holes", "Au_gmean", "Ag_gmean", "Cu_gmean", "As_gmean", "run_m",
                  "stability_median", "alt_mode", "ox_mode", "NAGpH_n", "NAGpH_lt45_share"]].round(3).to_string(index=False))

    # --- outputs ---------------------------------------------------------------------------
    pm = P.max(1)
    out = pd.DataFrame({"HoleID": c.SiteID, "From": c.DepthFrom})
    cols_ml = {"ML_hmm_status": state, "ML_hmm_nama": np.array(names)[state - 1], "ML_hmm_p_maks": pm.round(4),
               "ML_hmm_ambigu": np.where(pm < P_AMBIG, "Y", "N"), "ML_hmm_entropi": classify.entropy(P).round(4),
               **{f"ML_hmm_p_S{j + 1}": P[:, j].round(4) for j in range(K)},
               "ML_hmm_viterbi": vit, "ML_hmm_stabil": stab.round(3), "ML_hmm_gmm": gmm_lab}
    for k_, v in cols_ml.items():
        col = pd.Series(pd.NA, index=c.index, dtype="object")
        col.iloc[rows] = v
        out[k_] = col
    # +S sensitivity states as a column (rows with SCIS)
    col = pd.Series(pd.NA, index=c.index, dtype="object")
    col.iloc[rows[scis]] = lab_s
    out["ML_hmm_S_status"] = col
    assert len(out) == len(c) and not out.duplicated(["HoleID", "From"]).any()
    assert out.ML_hmm_status.notna().sum() == len(rows)
    ml_dir = paths.PROCESSED / "ml"
    out.to_csv(ml_dir / "komposit__ml4_hmm.csv", index=False)

    hyper = {"seed": SEED, "features": "log10 Au, Ag, Cu, As (komposit 1 m)", "K_grid": "2-8", "K_selected": K,
             "covariance": "full", "min_covar_scaled": min_covar, "n_iter": gs.N_ITER, "tol": gs.TOL,
             "restarts": RESTARTS, "restarts_cv": RESTARTS_CV, "draws": N_DRAWS, "draws_cv": N_DRAWS_CV,
             "boot_B": N_BOOT, "restarts_boot": RESTARTS_BOOT, "cens_share": CENS_SHARE,
             "cens_spread": "uniform log10 [DL/3, DL]", "n_composites": len(rows), "n_segments": len(lens),
             "boot_ari_median": float(np.median(ari_b)), "boot_ari_05": float(np.percentile(ari_b, 5)),
             "boot_ari_95": float(np.percentile(ari_b, 95))}
    summary = pd.concat([cvsum.assign(kind="K_selection"),
                         pd.DataFrame([{"kind": "hyperparameter", "name": k_, "value": v} for k_, v in hyper.items()])])
    summary.to_csv(paths.PROCESSED / "ml4_summary.csv", index=False)
    states.to_csv(paths.PROCESSED / "ml4_states.csv", index=False)
    pd.concat([pd.DataFrame(comp_rows), sens.assign(kind="sensitivity"), cont.assign(kind="continuity")]).to_csv(
        paths.PROCESSED / "ml4_comparisons.csv", index=False)
    cv.to_csv(paths.PROCESSED / "ml4_cv_folds.csv", index=False)

    # --- GIS ---------------------------------------------------------------------------------
    gk = c.loc[rows, ["SiteID", "DepthFrom", "DepthTo", "X_from", "Y_from", "Z_from", "X_mid", "Y_mid", "Z_mid",
                      "X_to", "Y_to", "Z_to", "AltFacies", "ox_state"]].reset_index(drop=True)
    for k_ in ("ML_hmm_status", "ML_hmm_nama", "ML_hmm_p_maks", "ML_hmm_ambigu", "ML_hmm_stabil"):
        gk[k_] = out.loc[rows, k_].to_numpy()
    gk["ML_hmm_status"] = gk.ML_hmm_status.astype(int)
    gk["ML_hmm_p_maks"] = gk.ML_hmm_p_maks.astype(float)
    gk["ML_hmm_stabil"] = gk.ML_hmm_stabil.astype(float)
    gpkg = paths.GIS / "ml4_hmm.gpkg"
    pts = gpd.GeoDataFrame(gk.drop(columns=[c_ for c_ in gk if c_.startswith(("X_", "Y_", "Z_"))]),
                           geometry=gpd.points_from_xy(gk.X_mid, gk.Y_mid, gk.Z_mid), crs=paths.CRS)
    seg_g = gpd.GeoDataFrame(pts.drop(columns="geometry"), geometry=shapely.linestrings(
        np.stack([gk[["X_from", "Y_from", "Z_from"]].to_numpy(), gk[["X_to", "Y_to", "Z_to"]].to_numpy()], axis=1)),
        crs=paths.CRS)
    for layer, gdf in (("komposit_status", pts), ("segmen_status", seg_g)):
        gdf.to_file(gpkg, layer=layer, driver="GPKG", mode="w")
        assert pyogrio.read_info(gpkg, layer=layer)["features"] == len(gdf)

    # --- figures -------------------------------------------------------------------------------
    fig_dir = paths.FIGURES
    cols = gs.state_colours(K)
    fig_k(cvsum, K, fig_dir / "11_pemilihan_K_v1.png")
    fig_profiles(c_ok, state, names, cols, fig_dir / "11_profil_status_v1.png")
    run_ci = [(np.percentile(B_run[:, j], 5), np.percentile(B_run[:, j], 95)) for j in range(K)]
    fig_transitions(T, run, run_ci, names, fig_dir / "11_matriks_transisi_v1.png")
    cfig = c.copy()
    for k_ in ("ML_hmm_status", "ML_hmm_ambigu"):
        cfig[k_] = out[k_]
    fig_strips(cfig, cols, names, fig_dir / "11_strip_log_v1.png")
    fig_continuity(cont, fig_dir / "11_kontinuitas_v1.png")
    print("palette:", ",".join(cols))
    print("done")


if __name__ == "__main__":
    main()
