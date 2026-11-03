"""ML-5: PAF/NAF classes, Mondrian conformal prediction and unsupervised clustering
(AGENTS.md §6 task 5). Plan: LOG.md, 2026-11-03 ML-5 entry.

Labels: RJDH012 NAG tests (NAF / PAF-LC / PAF-HC, `src/acid.py`). Classifiers (RF, logistic,
prior) on three feature sets (transfer, full RJDH012 suite, no sulfur), validated by leaving
out contiguous 10 m depth blocks (one hole: blocks stand in for groups). Cross-conformal
p-values give each interval a prediction set; coverage is checked by nested block CV. Every
assay interval in the database gets a tier (1 SCIS in domain, 2 SCIS out of domain, 3 S2 for
SCIS, 4 no S), a set, a conservative management class and, where the set is not a confident
singleton, a place on the NAG-testing list. Unsupervised: GMM on PCA of the RJDH012 full suite
(U1) and of the features shared by the SCIS holes (U2), scored against the NAG classes.
Reads data/interim/05_assay_joined.csv, 01_element_summary.csv,
data/processed/ml/assay__ml2_classify.csv; writes data/processed/ml/assay__ml5_paf.csv,
data/processed/ml5_*.csv, gis/ml5_paf.gpkg, outputs/figures/12_*_v1.png. Prints summaries only.
Run: uv run python scripts/14_ml5_paf.py  (then scripts/07_export.py)
"""
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio
import shap
from joblib import Parallel, delayed
from matplotlib.patches import FancyBboxPatch, Patch
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, confusion_matrix, log_loss
from sklearn.mixture import GaussianMixture

from src import acid, classify as cl, geostrat as gs, paths, thresholds as th, zonation as zn

SEED = 0
BLOCK_M = 10.0          # contiguous depth blocks (validation groups)
BLOCK_SENS = 20.0
ALPHA = 0.10
ALPHAS = (0.10, 0.20)
CAP_SENS = (5.0, 20.0)
P_CLIP = 1e-3           # probabilities clipped before log loss (RF can give exact 0)
CANDIDATES = [("rf", 1), ("rf", 5), ("rf", 20), ("logreg", None), ("dummy", None)]
U_KMAX = 6
N_DRAWS = 20            # dequantisation / censoring draws for the GMMs
N_BOOT = 200
FLOOR_LOG10 = 0.05      # ML-1 variance floor, in log10

CLS = list(acid.CLASSES)
CLS_SHORT = {"NAF": "NAF", "PAF-LC": "LC", "PAF-HC": "HC"}
C_CLS = {"NAF": "#4575b4", "PAF-LC": "#f4a582", "PAF-HC": "#b2182b"}
C_INK, C_INK2, C_NULL = "#0b0b0b", "#52514e", "#b9b8b2"
OX_COL = {"Oxide": "#d7301f", "Transition": "#fdbb84", "Sulphide": "#525252"}
OX_ID = {"Oxide": "Oksida", "Transition": "Transisi", "Sulphide": "Sulfida"}
OX_FROM_ML2 = {"Oksida": 0.0, "Transisi": 1.0, "Sulfida": 2.0}
CLS_ID = {"NAF": "NAF (tidak membentuk asam)", "PAF-LC": "PAF-LC (kapasitas rendah)",
          "PAF-HC": "PAF-HC (kapasitas tinggi)"}

NUM_T = {"S": "SCIS_PCT_ml", "Au": "AuPPM_ml", "Ag": "AgPPM_ml", "Cu": "CuPPM_ml", "As": "AsPPM_ml"}
NUM_FULL = {"S_total": "S_PCT_ml", "Fe": "FePCT_ml", "K": "KPCT_ml", "Ba": "BaPPM_ml", "Sr": "SrPPM_ml",
            "Zn": "ZnPPM_ml", "Mn": "MnPPM_ml", "Pb": "PbPPM_ml"}
ALT_KEEP = ("AA", "SI", "AR")
CAT = ["oks", "alt_AA", "alt_SI", "alt_AR", "pirit"]
FEATS = {"transfer": [*NUM_T, *CAT],
         "lengkap": [*NUM_T, *NUM_FULL, "S_total/S", *CAT],
         "tanpa_S": [k for k in NUM_T if k != "S"] + CAT}
FEAT_ID = {"S": "S (SCIS)", "S_total": "S total", "S_total/S": "S total / S (SCIS)", "oks": "Oksidasi",
           "alt_AA": "Alterasi AA", "alt_SI": "Alterasi SI", "alt_AR": "Alterasi AR", "pirit": "Pirit (tercatat di log)"}
U1_COLS = ["S_PCT", "SCIS_PCT", "FePCT", "KPCT", "BaPPM", "SrPPM", "ZnPPM", "MnPPM"]
U2_COLS = ["SCIS_PCT", "AuPPM", "AgPPM", "CuPPM", "AsPPM"]


def el(c: str) -> str:
    return c.removesuffix("PPM").removesuffix("_PCT").removesuffix("PCT")


# --- data and features ---------------------------------------------------------------
def load() -> pd.DataFrame:
    a = pd.read_csv(paths.INTERIM / "05_assay_joined.csv", low_memory=False)
    ml2 = pd.read_csv(paths.PROCESSED / "ml" / "assay__ml2_classify.csv", usecols=["SampleID", "ML_oks_prediksi"])
    a = a.merge(ml2, on="SampleID", how="left", validate="one_to_one")
    a["no_sample"] = a.no_sample.astype(bool)
    # oxidation: the log where present, the ML-2 prediction where the hole has no log (RJDH019)
    a["ox_rank_used"] = a.ox_rank.fillna(a.ML_oks_prediksi.map(OX_FROM_ML2))
    a["ox_src"] = np.where(a.ox_rank.notna(), "log", np.where(a.ox_rank_used.notna(), "ML-2", None))
    a["ox_used"] = a.ox_rank_used.map({0.0: "Oxide", 1.0: "Transition", 2.0: "Sulphide"})
    a["S_ml_used"] = a.SCIS_PCT_ml.fillna(a.S2_SPCT_ml)   # S2 stands in for SCIS (Tier 3)
    a["S_src"] = np.where(a.SCIS_PCT_ml.notna(), "SCIS", np.where(a.S2_SPCT_ml.notna(), "S2", "none"))
    cap = "NAGpH4.5_kgH2SO4/ton"
    a["nag_cls"] = acid.nag_class(a.NAGpH, a[cap])
    for c in CAP_SENS:
        a[f"nag_cls_{c:g}"] = acid.nag_class(a.NAGpH, a[cap], cap_cut=c)
    return a


def features(a: pd.DataFrame) -> pd.DataFrame:
    """All model features for every row (log10 values; oxidation 0/0.5/1; alteration and
    logged pyrite indicators, pyrite unknown = 0.5)."""
    X = cl.log_features(a, {**{k: v for k, v in NUM_T.items() if k != "S"}, "S": "S_ml_used", **NUM_FULL},
                        ratios=[("S_total", "S")])
    X["oks"] = a.ox_rank_used / 2
    for c in ALT_KEEP:
        X[f"alt_{c}"] = (a.AltFacies == c).astype(float)
    X["pirit"] = a.min_py.map({True: 1.0, False: 0.0}).astype(float).fillna(0.5)
    return X


def proba(model, X, classes=CLS) -> np.ndarray:
    return cl._proba(model, X, classes)


def make(kind: str, leaf):
    return cl.rf(leaf) if kind == "rf" else cl.MODELS[kind]()


def clip_logloss(y, P) -> float:
    Q = np.clip(P, P_CLIP, 1)
    return log_loss(y, Q / Q.sum(1, keepdims=True), labels=CLS)


# --- validation and conformal ---------------------------------------------------------
def cross_conformal(kind, leaf, X, y, blocks, Xnew) -> dict:
    """One model per held-out block: OOF probabilities for the training rows, and pooled
    Mondrian p-values plus mean probabilities for Xnew."""
    cal, test, P_oof = [], [], np.full((len(y), len(CLS)), np.nan)
    for b in np.unique(blocks):
        te = blocks == b
        m = make(kind, leaf).fit(X[~te], y[~te])
        P_oof[te] = proba(m, X[te])
        cal.append((P_oof[te], y[te]))
        test.append(proba(m, Xnew))
    return {"oof": P_oof, "pval": acid.mondrian_pvalues(cal, test), "P": np.mean(test, axis=0)}


def nested_job(kind, leaf, X, y, blocks, b):
    te = blocks == b
    r = cross_conformal(kind, leaf, X[~te], y[~te], blocks[~te], X[te])
    return np.flatnonzero(te), r["pval"], r["P"]


def nested(kind, leaf, X, y, blocks) -> tuple[np.ndarray, np.ndarray]:
    """p-values and probabilities for every labelled row from a cross-conformal predictor
    that never saw its block (honest coverage)."""
    res = Parallel(n_jobs=-1)(delayed(nested_job)(kind, leaf, X, y, blocks, b) for b in np.unique(blocks))
    pv, P = np.full((len(y), len(CLS)), np.nan), np.full((len(y), len(CLS)), np.nan)
    for idx, p, q in res:
        pv[idx], P[idx] = p, q
    assert not np.isnan(pv).any()
    return pv, P


def oof_job(fs, kind, leaf, X, y, blocks, bsize):
    r = cross_conformal(kind, leaf, X, y, blocks, X[:1])
    return fs, kind, leaf, bsize, r["oof"]


# --- unsupervised ---------------------------------------------------------------------
def censored_matrix(a: pd.DataFrame, rows: np.ndarray, cols: list[str], summ: pd.DataFrame):
    """Values (_ml), censored mask and DL per cell: the harmonised DL where Stage 1 set one,
    otherwise 2 × the DL/2 floor value (job-specific DLs)."""
    V = a.loc[rows, [f"{c}_ml" for c in cols]].to_numpy(float)
    cens = a.loc[rows, [f"{c}_cens_h" for c in cols]].fillna(False).astype(bool).to_numpy()
    dl = 2 * V
    for j, c in enumerate(cols):
        h = summ.loc[summ.dataset.eq("assay") & summ.column.eq(c), "harmonised_dl"]
        if len(h) and pd.notna(h.iloc[0]):
            dl[:, j] = float(h.iloc[0])
    return V, cens, dl


def gmm_fit(T, k, reg, n_init=10, seed=SEED) -> GaussianMixture:
    return GaussianMixture(k, covariance_type="full", reg_covar=reg, n_init=n_init, random_state=seed,
                           max_iter=500).fit(T)


def bic_or_inf(T, k, reg) -> float:
    g = gmm_fit(T, k, reg, n_init=3)
    return g.bic(T) if th.admissible(g, len(T)) else np.inf


def gmm_pipeline(V, cens, dl, kmax=U_KMAX, k_fixed=None) -> dict:
    """Censoring-aware log10 draws → median/MAD → PCA (Horn) → full-covariance GMM, K by BIC
    averaged over draws (inadmissible K = +inf). Clusters ordered by the first column (S)."""
    Ls = [gs.log_features(V, cens, dl, np.random.default_rng(SEED + d)) for d in range(N_DRAWS)]
    med, mad = zn.robust_params(Ls[0])
    Zs = [(L - med) / mad for L in Ls]
    n_pc, eig, null = zn.horn(Zs[0], seed=SEED)
    n_pc = max(n_pc, 1)
    pca = PCA(n_pc).fit(Zs[0])
    Ts = [pca.transform(Z) for Z in Zs]
    reg = float((FLOOR_LOG10 / np.median(mad)) ** 2)
    bic = pd.DataFrame({k: [bic_or_inf(T, k, reg) for T in Ts[:5]] for k in range(1, kmax + 1)}).mean()
    k = int(k_fixed or bic.idxmin())
    g = gmm_fit(Ts[0], k, reg)
    o = np.argsort(pca.inverse_transform(g.means_)[:, 0], kind="stable")
    P = np.mean([g.predict_proba(T) for T in Ts], axis=0)[:, o]
    return {"k": k, "bic": bic, "n_pc": n_pc, "eig": eig, "null": null, "pca": pca, "gmm": g, "order": o,
            "P": P, "lab": P.argmax(1) + 1, "T0": Ts[0], "reg": reg, "evr": pca.explained_variance_ratio_}


def boot_job(b, T0, k, reg, ref_means):
    rng = np.random.default_rng(SEED + 1000 + b)
    idx = rng.integers(0, len(T0), len(T0))
    g = gmm_fit(T0[idx], k, reg, n_init=3, seed=SEED + b)
    perm = gs.align(ref_means, g.means_)
    return g.predict_proba(T0)[:, perm].argmax(1) + 1


def name_clusters(lab, nag) -> dict:
    """Cluster -> 'Kn: majority NAG class (members with NAG)' or 'tanpa label'."""
    out = {}
    for c in np.unique(lab):
        v = pd.Series(nag[(lab == c) & pd.notna(nag)])
        out[c] = (f"K{c}: {v.mode().iloc[0]} ({v.value_counts().max()}/{len(v)})" if len(v) else f"K{c}: tanpa label")
    return out


# --- main -----------------------------------------------------------------------------
def main() -> None:
    ml_dir = paths.PROCESSED / "ml"
    a = load()
    summ = pd.read_csv(paths.INTERIM / "01_element_summary.csv")
    X_all = features(a)
    rows_sum = []

    def rec(section, item, value):
        rows_sum.append({"bagian": section, "item": item, "nilai": value})

    # --- labels -----------------------------------------------------------------------
    lab = a.nag_cls.notna().to_numpy()
    d = a[lab].sort_values("DepthFrom")
    li = d.index.to_numpy()
    y = d.nag_cls.to_numpy(object)
    counts = pd.Series(y).value_counts().reindex(CLS).fillna(0).astype(int)
    print("NAG classes:", counts.to_dict(), "| by oxidation:",
          pd.crosstab(d.ox_state, d.nag_cls).reindex(columns=CLS, fill_value=0).to_dict("index"))
    assert counts.tolist() == [37, 48, 21], "label counts differ from the plan profiling"
    cap_cens = d["NAGpH4.5_kgH2SO4/ton_cens"].fillna(False).astype(bool)
    assert cap_cens[d.nag_cls.eq("NAF")].all(), "a NAF row has an uncensored NAG capacity"
    for c in CAP_SENS:
        s = d[f"nag_cls_{c:g}"]
        rec("label", f"kelas pada batas {c:g} kg/t", str(s.value_counts().reindex(CLS).fillna(0).astype(int).to_dict()))
        rec("label", f"baris berubah kelas (batas {c:g} vs 10)", int((s != d.nag_cls).sum()))
    for c in CLS:
        rec("label", f"n {c}", int(counts[c]))

    # --- NAPP proxy (descriptive; lab's own Ca/Mg values) -------------------------------
    napp = acid.napp_proxy(d.SCIS_PCT, d.S_PCT, d.CaPCT, d.MgPCT).set_index(d.index)
    napp["kelas"] = y
    napp_tab = napp.groupby("kelas")[["MPA_SCIS", "MPA_total", "ANC_maks", "NAPP_min_SCIS", "NAPP_min_total"]] \
        .median().reindex(CLS)
    napp_tab["n"] = counts
    napp_tab["NAPP_min_SCIS_gt0"] = napp.groupby("kelas").NAPP_min_SCIS.apply(lambda v: int((v > 0).sum()))
    napp_tab["NAPP_min_SCIS_gt10"] = napp.groupby("kelas").NAPP_min_SCIS.apply(lambda v: int((v > 10).sum()))
    napp_tab["NAPP_min_total_gt0"] = napp.groupby("kelas").NAPP_min_total.apply(lambda v: int((v > 0).sum()))
    print("\nNAPP proxy (median kg H2SO4/t per class):\n" + napp_tab.round(2).to_string())

    # --- model selection: plain leave-one-block-out OOF ----------------------------------
    blocks = {bs: acid.depth_blocks(d.DepthFrom, bs) for bs in (BLOCK_M, BLOCK_SENS)}
    rec("validasi", "blok 10 m", len(np.unique(blocks[BLOCK_M])))
    rec("validasi", "blok 20 m", len(np.unique(blocks[BLOCK_SENS])))
    XF = {fs: X_all.loc[li, cols].to_numpy(float) for fs, cols in FEATS.items()}
    for fs, Xf in XF.items():
        assert not np.isnan(Xf).any(), f"{fs}: NaN feature in RJDH012"
    jobs = [(fs, k, lf, XF[fs], y, blocks[bs], bs) for fs in FEATS for k, lf in CANDIDATES for bs in (BLOCK_M, BLOCK_SENS)]
    res = Parallel(n_jobs=-1)(delayed(oof_job)(*j) for j in jobs)
    sc_rows, oof = [], {}
    for fs, kind, leaf, bs, P in res:
        s = cl.scores(y, P, CLS)
        ci = cl.group_bootstrap(y, cl.predict(P, CLS), blocks[bs], B=1000) if kind != "dummy" else (np.nan, np.nan)
        sc_rows.append({"fitur": fs, "model": kind, "leaf": leaf, "blok_m": bs, "log_loss": clip_logloss(y, P),
                        **s, "bal_acc_ci05": ci[0], "bal_acc_ci95": ci[1]})
        oof[(fs, kind, leaf, bs)] = P
    sc = pd.DataFrame(sc_rows)
    best = {}
    for fs in FEATS:
        r = sc[(sc.fitur == fs) & (sc.blok_m == BLOCK_M) & (sc.model != "dummy")].sort_values(["log_loss", "bal_acc"],
                                                                                            ascending=[True, False])
        best[fs] = (r.iloc[0].model, None if pd.isna(r.iloc[0].leaf) else int(r.iloc[0].leaf))
    sc["dipilih"] = [best[r.fitur] == (r.model, None if pd.isna(r.leaf) else int(r.leaf)) for r in sc.itertuples()]
    print("\nmodel selection (10 m blocks; log loss, balanced accuracy, kappa):")
    print(sc[sc.blok_m == BLOCK_M][["fitur", "model", "leaf", "log_loss", "bal_acc", "kappa", "recall_NAF",
                                    "recall_PAF-LC", "recall_PAF-HC", "dipilih"]].round(3).to_string(index=False))

    # --- conformal: nested coverage ------------------------------------------------------
    conf_rows, nest = [], {}
    for fs in FEATS:
        kind, leaf = best[fs]
        for bs in (BLOCK_M, BLOCK_SENS) if fs == "transfer" else (BLOCK_M,):
            pv, Pn = nested(kind, leaf, XF[fs], y, blocks[bs])
            nest[(fs, bs)] = (pv, Pn)
            for al in ALPHAS:
                S = acid.prediction_sets(pv, al)
                for subset, m in (("semua", np.ones(len(y), bool)), ("Oksida", d.ox_state.eq("Oxide").to_numpy()),
                                  ("Sulfida", d.ox_state.eq("Sulphide").to_numpy())):
                    t = acid.coverage(y[m], S[m])
                    conf_rows += [{"fitur": fs, "model": kind, "leaf": leaf, "blok_m": bs, "alpha": al, "subset": subset,
                                   **r} for r in t.to_dict("records")]
                    if subset == "semua":
                        lbl = pd.Series(acid.set_label(S))
                        for setname, n in lbl.value_counts().items():
                            conf_rows.append({"fitur": fs, "model": kind, "leaf": leaf, "blok_m": bs, "alpha": al,
                                              "subset": "set", "kelas": setname, "n": int(n)})
    conf = pd.DataFrame(conf_rows)
    show = conf[(conf.blok_m == BLOCK_M) & (conf.subset != "set")]
    print("\nnested cross-conformal coverage (10 m blocks):")
    print(show[["fitur", "alpha", "subset", "kelas", "n", "cakupan", "ukuran_set", "singleton"]].round(3)
          .to_string(index=False))
    pv_main = nest[("transfer", BLOCK_M)][0]
    S_main = acid.prediction_sets(pv_main, ALPHA)
    print("\nRJDH012 sets (transfer, alpha 0.10) by true class:")
    print(pd.crosstab(pd.Series(y, name="NAG"), pd.Series(acid.set_label(S_main), name="set")).to_string())

    # --- final models on all labelled rows; database prediction --------------------------
    ok = ~a.no_sample.to_numpy()
    tr_rng = {f: (X_all.loc[li, f].min(), X_all.loc[li, f].max()) for f in FEATS["transfer"]}
    out_parts = []
    for f in [*NUM_T]:
        lo, hi = tr_rng[f]
        v = X_all[f]
        out_parts.append(np.where(v > hi + 1e-9, f"{f}>maks", np.where(v < lo - 1e-9, f"{f}<min", "")))
    out_parts.append(np.where(a.ox_used.eq("Transition"), "Transisi", ""))
    out_parts.append(np.where(~a.AltFacies.isin([*ALT_KEEP, "UA"]), "alterasi_" + a.AltFacies.astype(str), ""))
    out_parts.append(np.where(a.ox_src.eq("ML-2"), "oksidasi_ML2", ""))
    reason = pd.Series([";".join(p for p in parts if p) for parts in zip(*out_parts)], index=a.index)
    reason_noS = reason.str.replace(r"S[<>](maks|min);?", "", regex=True).str.strip(";")
    has_scis = a.S_src.eq("SCIS")
    oor = reason.str.contains(r"[<>]|alterasi_", regex=True)
    tiers = pd.Series(acid.tier(has_scis, a.S_src.eq("S2"), a.ox_used.eq("Transition"), oor), index=a.index)
    tiers[~ok] = 0
    reason = reason.where(tiers.isin([1, 2, 3]), reason_noS)

    pval = np.full((len(a), len(CLS)), np.nan)
    P = np.full((len(a), len(CLS)), np.nan)
    model_used = pd.Series(None, index=a.index, dtype=object)
    for fs, rows in (("transfer", ok & tiers.isin([1, 2, 3]).to_numpy()), ("tanpa_S", ok & tiers.eq(4).to_numpy())):
        kind, leaf = best[fs]
        Xn = X_all.loc[rows, FEATS[fs]].to_numpy(float)
        assert not np.isnan(Xn).any(), f"{fs}: NaN feature in prediction rows"
        r = cross_conformal(kind, leaf, XF[fs], y, blocks[BLOCK_M], Xn)
        pval[rows], P[rows] = r["pval"], r["P"]
        model_used[rows] = fs
    # labelled rows: honest (nested) values from the transfer model
    pos = a.index.get_indexer(li)
    pval[pos], P[pos] = nest[("transfer", BLOCK_M)]
    assert not np.isnan(pval[ok]).any() and np.isnan(pval[~ok]).all()

    S = acid.prediction_sets(np.nan_to_num(pval, nan=0), ALPHA)
    nset = S.sum(1)
    setlab = pd.Series(acid.set_label(S), index=a.index)
    kelas = pd.Series(np.where(nset == 1, setlab, "ambigu"), index=a.index)
    kelola = pd.Series(acid.manage(S, np.nan_to_num(pval, nan=0)), index=a.index)
    kelola[lab] = a.nag_cls[lab]
    kelola_src = pd.Series(np.where(lab, "uji_NAG", "ML"), index=a.index)
    hc_unsure = S[:, 2] & (nset > 1) | (nset == 0)
    prio = pd.Series(np.select([hc_unsure, setlab.eq("NAF|PAF-LC"), tiers.ge(2) & (nset == 1)],
                               ["1_HC_tidak_pasti", "2_NAF_atau_LC", "3_luar_domain"], ""), index=a.index)
    prio[lab | ~ok] = ""
    uji = prio.ne("")

    for frame in (setlab, kelas, kelola, kelola_src):
        frame[~ok] = None
    ml = pd.DataFrame({"SampleID": a.SampleID})
    ml["ML_paf_label"] = a.nag_cls
    ml["ML_paf_set"] = setlab
    ml["ML_paf_n_set"] = pd.Series(np.where(ok, nset, np.nan), index=a.index)
    ml["ML_paf_kelas"] = kelas
    ml["ML_paf_kelola"] = kelola
    ml["ML_paf_kelola_sumber"] = kelola_src
    for j, c in enumerate(CLS):
        ml[f"ML_paf_p_{CLS_SHORT[c]}"] = np.round(P[:, j], 4)
    for j, c in enumerate(CLS):
        ml[f"ML_paf_pval_{CLS_SHORT[c]}"] = np.round(pval[:, j], 4)
    ml["ML_paf_tier"] = tiers.where(tiers > 0)
    ml["ML_paf_model"] = model_used
    ml["ML_paf_luar_domain"] = np.where(ok, np.where(reason.ne(""), "Y", "N"), None)
    ml["ML_paf_alasan"] = reason.where(ok & reason.ne(""))
    ml["ML_paf_uji_NAG"] = np.where(ok, np.where(uji, "Y", "N"), None)
    ml["ML_paf_prioritas_uji"] = prio.where(uji)
    ml["ML_paf_napp_min"] = np.nan
    ml.loc[napp.index, "ML_paf_napp_min"] = napp.NAPP_min_SCIS.round(2)

    # --- unsupervised ----------------------------------------------------------------------
    u1_rows = (a.SiteID.eq("RJDH012") & ok & a[[f"{c}_ml" for c in U1_COLS]].notna().all(1)).to_numpy()
    V, cens, dl = censored_matrix(a, u1_rows, U1_COLS, summ)
    U1 = gmm_pipeline(V, cens, dl)
    U1_3 = gmm_pipeline(V, cens, dl, k_fixed=3)
    nag_u1 = a.nag_cls[u1_rows].to_numpy(object)
    ox_u1 = a.ox_used[u1_rows].to_numpy(object)
    oxi = (a.ox_used[u1_rows] == "Oxide").to_numpy()
    U1_ox = gmm_pipeline(V[oxi], cens[oxi], dl[oxi])
    u2_rows = (ok & has_scis.to_numpy() & a[[f"{c}_ml" for c in U2_COLS]].notna().all(1).to_numpy())
    V2, cens2, dl2 = censored_matrix(a, u2_rows, U2_COLS, summ)
    U2 = gmm_pipeline(V2, cens2, dl2)
    ref = U2["gmm"].means_[U2["order"]]
    boot = np.array(Parallel(n_jobs=-1)(delayed(boot_job)(b, U2["T0"], U2["k"], U2["reg"], ref) for b in range(N_BOOT)))
    lab2_main = U2["gmm"].predict_proba(U2["T0"])[:, U2["order"]].argmax(1) + 1
    stab2 = zn.stability(lab2_main, boot)
    ari2 = zn.boot_ari(lab2_main, boot)
    nag_u2 = a.nag_cls[u2_rows].to_numpy(object)
    names2 = {int(k): v for k, v in name_clusters(U2["lab"], nag_u2).items()}
    ml["ML_paf_gmm"] = np.nan
    ml.loc[u2_rows, "ML_paf_gmm"] = U2["lab"]
    ml["ML_paf_gmm_nama"] = None
    ml.loc[u2_rows, "ML_paf_gmm_nama"] = pd.Series(U2["lab"]).map(names2).to_numpy()
    ml["ML_paf_gmm_p_maks"] = np.nan
    ml.loc[u2_rows, "ML_paf_gmm_p_maks"] = U2["P"].max(1).round(4)
    ml["ML_paf_gmm_stabil"] = np.nan
    ml.loc[u2_rows, "ML_paf_gmm_stabil"] = stab2.round(3)

    clus_rows = []

    def clus_eval(name, U, nag, ox, extra=None):
        m = pd.notna(nag)
        labs = U["lab"]
        binary = np.where(nag[m] == "NAF", "NAF", "PAF")
        e = {"model": name, "n": len(labs), "K": U["k"], "n_PC": U["n_pc"],
             "var_PC": float(np.sum(U["evr"])), "n_label": int(m.sum()),
             "ARI_NAG3": adjusted_rand_score(nag[m], labs[m]), "V_NAG3": zn.cramers_v(nag[m], labs[m]),
             "ARI_PAF_NAF": adjusted_rand_score(binary, labs[m]), "V_PAF_NAF": zn.cramers_v(binary, labs[m]),
             "ARI_oks": adjusted_rand_score(ox[pd.notna(ox)], labs[pd.notna(ox)]),
             "V_oks": zn.cramers_v(ox[pd.notna(ox)], labs[pd.notna(ox)]), **(extra or {})}
        for k, v in U["bic"].items():
            e[f"dBIC_K{k}"] = v - U["bic"].min() if np.isfinite(v) else np.inf
        clus_rows.append(e)
        t = pd.crosstab(pd.Series(labs[m], name="klaster"), pd.Series(nag[m], name="NAG")).reindex(columns=CLS,
                                                                                                fill_value=0)
        return t

    t_u1 = clus_eval("U1", U1, nag_u1, ox_u1)
    t_u13 = clus_eval("U1_K3", U1_3, nag_u1, ox_u1)
    clus_eval("U1_oksida", U1_ox, nag_u1[oxi], ox_u1[oxi])
    kel2 = kelola[u2_rows].to_numpy(object)
    t_u2 = clus_eval("U2", U2, nag_u2, a.ox_used[u2_rows].to_numpy(object),
                     {"ARI_kelola": adjusted_rand_score(kel2, U2["lab"]), "V_kelola": zn.cramers_v(kel2, U2["lab"]),
                      "boot_ARI_med": float(np.median(ari2)), "boot_ARI_05": float(np.percentile(ari2, 5)),
                      "boot_ARI_95": float(np.percentile(ari2, 95)), "stabil_med": float(np.median(stab2))})
    clus = pd.DataFrame(clus_rows)
    u1_pca = pd.DataFrame(U1["pca"].components_.T, index=[el(c) for c in U1_COLS],
                          columns=[f"PC{i + 1}" for i in range(U1["n_pc"])])
    u2_pca = pd.DataFrame(U2["pca"].components_.T, index=[el(c) for c in U2_COLS],
                          columns=[f"PC{i + 1}" for i in range(U2["n_pc"])])
    print("\nunsupervised:")
    print(clus.round(3).to_string(index=False))
    print("U1 crosstab:\n" + t_u1.to_string(), "\nU1 K3 crosstab:\n" + t_u13.to_string(),
          "\nU2 crosstab (RJDH012 members):\n" + t_u2.to_string())
    print("U1 loadings:\n" + u1_pca.round(2).to_string(), "\nU2 loadings:\n" + u2_pca.round(2).to_string())
    print("U2 names:", names2)
    u2_med = pd.DataFrame(V2, columns=[el(c) for c in U2_COLS]).groupby(U2["lab"]).median()
    u2_med["n"] = pd.Series(U2["lab"]).value_counts().sort_index()
    u2_med["kelola_HC"] = pd.Series(kel2 == "PAF-HC").groupby(U2["lab"]).mean()
    print("U2 cluster medians:\n" + u2_med.round(3).to_string())
    print("U2 vs management class:\n" + pd.crosstab(pd.Series(U2["lab"], name="klaster"),
                                                     pd.Series(kel2, name="kelola")).to_string())

    # --- checks -------------------------------------------------------------------------------
    assert ml.loc[a.no_sample.to_numpy(), [c for c in ml if c.startswith("ML_paf") and c not in
                                           ("ML_paf_label", "ML_paf_napp_min")]].isna().all().all()
    assert ml.ML_paf_tier[ok].notna().all()
    assert (ml.ML_paf_uji_NAG[ok & tiers.ge(2).to_numpy() & ~lab & (nset == 1)] == "Y").all()
    assert (ml.ML_paf_kelola[lab] == a.nag_cls[lab]).all()
    assert len(ml) == len(a) and ml.SampleID.is_unique
    ml_path = ml_dir / "assay__ml5_paf.csv"
    ml.to_csv(ml_path, index=False)

    # --- summaries ------------------------------------------------------------------------------
    an = a[ok].assign(len_m=lambda x: x.DepthTo - x.DepthFrom, kelola=kelola[ok], tier=tiers[ok], uji=uji[ok],
                      setlab=setlab[ok])
    per_hole = an.pivot_table(index="SiteID", columns="kelola", values="len_m", aggfunc="sum", fill_value=0) \
        .reindex(columns=CLS, fill_value=0)
    per_hole.columns = [f"m_{c}" for c in per_hole.columns]
    tier_m = an.pivot_table(index="SiteID", columns="tier", values="len_m", aggfunc="sum", fill_value=0)
    tier_m.columns = [f"m_tier{c}" for c in tier_m.columns]
    # confident PAF-HC: measured by NAG, or a single-class ML set on an untested interval
    tested = pd.Series(lab, index=a.index)[ok]
    hc_sure = tested & an.kelola.eq("PAF-HC") | ~tested & an.setlab.eq("PAF-HC")
    per_hole = (per_hole.join(tier_m)
                .join(an.len_m.where(an.uji, 0).groupby(an.SiteID).sum().rename("m_uji_NAG"))
                .join(an.len_m.where(hc_sure, 0).groupby(an.SiteID).sum().rename("m_PAF-HC_pasti")))
    per_hole.loc["TOTAL"] = per_hole.sum()
    print("\nmetres per hole (management class, tier, NAG testing):\n" + per_hole.round(1).to_string())
    for t in (1, 2, 3, 4):
        m = an.tier == t
        rec("prediksi", f"tier {t} baris", int(m.sum()))
        rec("prediksi", f"tier {t} singleton", float((S[ok][m.to_numpy()].sum(1) == 1).mean()) if m.any() else np.nan)
        for c in CLS:
            rec("prediksi", f"tier {t} kelola {c} (m)", float(an.len_m[m & an.kelola.eq(c)].sum()))
    rec("prediksi", "set terbanyak", str(an.setlab.value_counts().head(6).to_dict()))
    rec("prediksi", "alasan luar domain", str(reason[ok & reason.ne("")].str.split(";").explode().value_counts().to_dict()))

    runs = acid.merge_runs(a[ok & uji.to_numpy()].assign(prioritas=prio, kelola=kelola, tier=tiers)
                           [["SiteID", "DepthFrom", "DepthTo", "prioritas", "kelola", "tier"]],
                           ["prioritas", "kelola", "tier"])
    runs = runs.sort_values(["prioritas", "tier", "length_m"], ascending=[True, True, False]).reset_index(drop=True)
    print("\nNAG-testing list: runs per priority (n, metres):\n"
          + runs.groupby("prioritas").length_m.agg(["size", "sum"]).round(1).to_string())

    for fs in FEATS:
        rec("model", f"{fs} dipilih", f"{best[fs][0]} leaf {best[fs][1]}")
    rec("u1", "baris", int(u1_rows.sum()))
    rec("u2", "baris", int(u2_rows.sum()))
    rec("u2", "nama klaster", str(names2))
    summary = pd.DataFrame(rows_sum)
    P_ = paths.PROCESSED
    summary.to_csv(P_ / "ml5_summary.csv", index=False)
    sc.to_csv(P_ / "ml5_scores.csv", index=False)
    conf.to_csv(P_ / "ml5_conformal.csv", index=False)
    runs.to_csv(P_ / "ml5_uji_nag.csv", index=False)
    per_hole.reset_index().to_csv(P_ / "ml5_per_hole.csv", index=False)
    napp_tab.reset_index().to_csv(P_ / "ml5_napp.csv", index=False)
    pd.concat([clus, pd.concat({"U1": t_u1, "U1_K3": t_u13, "U2": t_u2}).reset_index()
               .rename(columns={"level_0": "model"})], ignore_index=True).to_csv(P_ / "ml5_clusters.csv", index=False)

    # --- GIS ----------------------------------------------------------------------------------
    g = a.loc[ok, ["SampleID", "SiteID", "DepthFrom", "DepthTo", "X_mid", "Y_mid", "Z_mid"]].join(
        ml.loc[ok, ["ML_paf_kelola", "ML_paf_set", "ML_paf_tier", "ML_paf_uji_NAG", "ML_paf_label"]])
    gdf = gpd.GeoDataFrame(g.drop(columns=["X_mid", "Y_mid", "Z_mid"]),
                           geometry=gpd.points_from_xy(g.X_mid, g.Y_mid, g.Z_mid), crs=paths.CRS)
    gpkg = paths.GIS / "ml5_paf.gpkg"
    gdf.to_file(gpkg, layer="interval_paf", driver="GPKG", mode="w")
    assert pyogrio.read_info(gpkg, layer="interval_paf")["features"] == len(gdf)

    # --- figures -------------------------------------------------------------------------------
    F = paths.FIGURES
    fig_flowchart(F / "12_diagram_alir_paf_naf_v1.png")
    fig_nag(d, F / "12_nag_ph_kapasitas_v1.png")
    fig_profile(d, S_main, F / "12_profil_rjdh012_v1.png")
    fig_coverage(conf, F / "12_cakupan_konformal_v1.png")
    fig_confusion(y, {fs: oof[(fs, *best[fs], BLOCK_M)] for fs in FEATS}, best, F / "12_matriks_kebingungan_v1.png")
    fig_shap(XF["lengkap"], y, F / "12_shap_lengkap_v1.png")
    fig_gmm(U1, t_u1, U2, t_u2, F / "12_gmm_u1_u2_v1.png")
    fig_holes(per_hole.drop(index="TOTAL"), F / "12_ringkasan_lubang_v1.png")
    fig_napp(napp, F / "12_napp_proksi_v1.png")
    print(f"\noutputs: {ml_path.relative_to(paths.ROOT)}; data/processed/ml5_*.csv; gis/ml5_paf.gpkg "
          f"({len(gdf)}); outputs/figures/12_*_v1.png")


# --- figures ---------------------------------------------------------------------------------
def _clean(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def _save(fig, path):
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_flowchart(path) -> None:
    fig, ax = plt.subplots(figsize=(8.3, 10.5))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 130)
    ax.axis("off")

    def box(x, y, w, h, text, fc="#f4f3ee", ec=C_INK, fs=8, bold=False):
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.6,rounding_size=1.5",
                                    fc=fc, ec=ec, lw=1))
        ax.text(x, y, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal", wrap=True)

    def arrow(x0, y0, x1, y1, label=None, side="right"):
        ax.annotate("", (x1, y1), (x0, y0), arrowprops=dict(arrowstyle="-|>", color=C_INK2, lw=1))
        if label:
            ax.text((x0 + x1) / 2 + (1.5 if side == "right" else -1.5), (y0 + y1) / 2, label, fontsize=7.5,
                    ha="left" if side == "right" else "right", va="center", color=C_INK2)

    box(50, 125, 60, 6, "Sampel batuan / interval bor (calon batuan buangan)", bold=True)
    box(50, 113, 34, 6, "Ada uji NAG?", fc="#ffffff")
    arrow(50, 122, 50, 116)
    # left branch: NAG rules
    box(22, 100, 34, 7, "NAG pH ≥ 4,5 ?", fc="#ffffff")
    arrow(40, 111, 25, 103.5, "Ya", side="left")
    box(10, 86, 14, 7, "NAF", fc=C_CLS["NAF"], fs=9, bold=True)
    arrow(17, 96.5, 11, 89.5, "Ya", side="left")
    box(32, 86, 25, 8, "Kapasitas NAG (pH 4,5)\n≥ 10 kg H₂SO₄/t ?", fc="#ffffff")
    arrow(27, 96.5, 32, 90, "Tidak")
    box(23, 70, 15, 7, "PAF-HC", fc=C_CLS["PAF-HC"], fs=9, bold=True)
    box(44, 70, 15, 7, "PAF-LC", fc=C_CLS["PAF-LC"], fs=9, bold=True)
    arrow(29, 82, 23, 73.5, "Ya", side="left")
    arrow(36, 82, 44, 73.5, "Tidak")
    # right branch: ML
    box(76, 100, 38, 9, "Tingkat data (tier)\n1 SCIS dalam domain · 2 SCIS luar domain\n3 S2 pengganti SCIS · 4 tanpa S",
        fc="#ffffff", fs=7.5)
    arrow(60, 111, 74, 104.5, "Tidak")
    box(76, 86, 38, 8, "Model ML (latih: RJDH012)\n+ prediksi konformal Mondrian (α = 0,10)", fs=7.5)
    arrow(76, 95.5, 76, 90)
    box(76, 72, 38, 8, "Set prediksi berisi satu kelas\ndan tier 1 ?", fc="#ffffff", fs=7.5)
    arrow(76, 82, 76, 76)
    box(64, 57, 22, 8, "Kelas ML\n(NAF / PAF-LC / PAF-HC)", fs=7.5)
    box(89, 57, 20, 9, "Ambigu / luar domain:\nusulan uji NAG", fc="#fff1d6", fs=7.5)
    arrow(71, 68, 64, 61, "Ya", side="left")
    arrow(81, 68, 89, 61.5, "Tidak")
    box(76, 42, 46, 8, "Kelas pengelolaan konservatif:\nkelas paling berisiko di dalam set prediksi", fs=7.5)
    arrow(64, 53, 72, 46)
    arrow(89, 52.5, 80, 46)
    # handling
    box(50, 25, 92, 14, "Pengelolaan (indikatif):\n"
        "NAF: timbunan umum / material konstruksi setelah verifikasi uji\n"
        "PAF-LC: enkapsulasi di dalam timbunan, penutup tanah, pengendalian air limpasan\n"
        "PAF-HC: enkapsulasi di inti timbunan, penutup kedap / sub-akuatik, kolam pengendap,\n"
        "pengolahan air asam (kapur), pemantauan pH dan logam", fs=7.5)
    for x0, y0 in ((10, 82.5), (23, 66.5), (44, 66.5), (76, 38)):
        arrow(x0, y0, max(min(x0, 90), 10), 32.5)
    ax.text(50, 8, "Batas kelas mengikuti AMIRA (2002) dengan kapasitas NAG menggantikan NAPP (ANC tidak diukur) [VERIFIKASI].\n"
            "Kelas pengelolaan berlaku untuk material serupa RJDH012; tier 2–4 dan set ambigu perlu uji NAG.",
            ha="center", va="center", fontsize=7, color=C_INK2)
    ax.set_title("Diagram alir klasifikasi PAF/NAF batuan buangan, prospek Ramba Joring", fontsize=11)
    _save(fig, path)


def fig_nag(d, path) -> None:
    cap = d["NAGpH4.5_kgH2SO4/ton"].clip(lower=0.003)
    fig, ax = plt.subplots(figsize=(6.8, 4.6))
    for ox, col in OX_COL.items():
        m = d.ox_state.eq(ox)
        if m.any():
            ax.scatter(d.NAGpH[m], cap[m], s=22, c=col, edgecolor="white", lw=0.5, label=f"{OX_ID[ox]} (n {m.sum()})")
    ax.set_yscale("log")
    ax.axvline(acid.PH_CUT, color=C_INK, lw=1, ls="--")
    ax.axhline(acid.CAP_CUT, xmax=(acid.PH_CUT - 1.5) / 6, color=C_INK, lw=1, ls="--")
    ax.set_xlim(1.5, 7.5)
    for x, yv, t in ((6.0, 0.02, "NAF"), (3.4, 30, "PAF-HC"), (3.6, 0.5, "PAF-LC")):
        ax.text(x, yv, f"{t}\n(n {int(d.nag_cls.eq(t).sum())})", ha="center", fontsize=8.5, fontweight="bold",
                color=C_CLS[t])
    ax.text(4.55, 150, "NAG pH 4,5", fontsize=7.5, color=C_INK2)
    ax.text(1.6, 12, "10 kg H₂SO₄/t", fontsize=7.5, color=C_INK2)
    ax.text(7.4, 20, "baris terbawah: kapasitas\ndi bawah batas deteksi", ha="right", fontsize=6.5, color=C_INK2)
    ax.set_xlabel("NAG pH", fontsize=9)
    ax.set_ylabel("Kapasitas NAG hingga pH 4,5 (kg H₂SO₄/t, skala log)", fontsize=9)
    ax.legend(fontsize=7.5, frameon=False, loc="upper right")
    _clean(ax)
    ax.set_title("Kelas NAF / PAF-LC / PAF-HC dari uji NAG (RJDH012, n 106)", fontsize=10)
    _save(fig, path)


def fig_profile(d, S, path) -> None:
    top, bot = d.DepthFrom.to_numpy(), d.DepthTo.to_numpy()
    fig, axes = plt.subplots(1, 5, figsize=(9.5, 8.5), sharey=True, gridspec_kw={"width_ratios": [2.2, 1.6, 0.6, 0.6, 1.4]})
    ax = axes[0]
    mid = (top + bot) / 2
    ax.plot(d.SCIS_PCT, mid, "-o", ms=2.5, color=C_INK, lw=0.8, label="S (SCIS)")
    ax.plot(d.S_PCT, mid, "-o", ms=2.5, color=C_NULL, lw=0.8, label="S total")
    ax.set_xscale("log")
    ax.set_xlabel("S (%)", fontsize=8.5)
    ax.legend(fontsize=7, frameon=False, loc="lower left")
    ax.set_ylabel("Kedalaman (m)", fontsize=9)
    ax = axes[1]
    ax.plot(d.NAGpH, mid, "-o", ms=2.5, color=C_INK, lw=0.8)
    ax.axvline(acid.PH_CUT, color=C_INK2, ls="--", lw=0.8)
    ax.set_xlabel("NAG pH", fontsize=8.5)

    def strip(ax, col, title):
        for t, b, c in zip(top, bot, col):
            ax.fill_betweenx([t, b], 0, 1, color=c, lw=0)
        ax.set_xticks([])
        ax.set_title(title, fontsize=8)

    strip(axes[2], [OX_COL.get(o, C_NULL) for o in d.ox_state], "Oksidasi")
    strip(axes[3], [C_CLS[c] for c in d.nag_cls], "Kelas\nNAG")
    ax = axes[4]
    for t, b, row in zip(top, bot, S):
        for j, c in enumerate(CLS):
            if row[j]:
                ax.fill_betweenx([t, b], j, j + 0.9, color=C_CLS[c], lw=0)
    ax.set_xticks([0.45, 1.45, 2.45], ["NAF", "LC", "HC"], fontsize=7.5)
    ax.set_title("Set prediksi\n(α 0,10, CV bersarang)", fontsize=8)
    axes[0].invert_yaxis()
    for ax in axes:
        _clean(ax)
        ax.tick_params(labelsize=7.5)
    fig.legend(handles=[Patch(color=OX_COL[o], label=OX_ID[o]) for o in ("Oxide", "Sulphide")]
               + [Patch(color=C_CLS[c], label=CLS_ID[c]) for c in CLS], fontsize=7.5, frameon=False, ncol=3,
               loc="lower center", bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("RJDH012: sulfur, NAG pH, kelas NAG dan set prediksi konformal", fontsize=10)
    fig.tight_layout()
    _save(fig, path)


def fig_coverage(conf, path) -> None:
    c = conf[(conf.blok_m == BLOCK_M) & (conf.subset == "semua") & conf.kelas.isin(CLS)]
    fsets = list(FEATS)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    w = 0.12
    for i, fs in enumerate(fsets):
        for k, al in enumerate(ALPHAS):
            r = c[(c.fitur == fs) & (c.alpha == al)].set_index("kelas").reindex(CLS)
            x = np.arange(len(CLS)) + (i * 2 + k - 2.5) * w
            hatch = "" if al == ALPHA else "///"
            axes[0].bar(x, r.cakupan, w, color=["#4c72b0", "#dd8452", "#55a868"][i], hatch=hatch, edgecolor="white",
                        label=f"{fs}, α {al:.2f}".replace(".", ","))
            axes[1].bar(x, r.ukuran_set, w, color=["#4c72b0", "#dd8452", "#55a868"][i], hatch=hatch, edgecolor="white")
    for al, ls in zip(ALPHAS, ("--", ":")):
        axes[0].axhline(1 - al, color=C_INK, lw=0.8, ls=ls)
    for ax, lab in zip(axes, ("Cakupan kelas sebenarnya", "Rata-rata ukuran set (jumlah kelas)")):
        ax.set_xticks(range(len(CLS)), CLS, fontsize=8.5)
        ax.set_ylabel(lab, fontsize=8.5)
        _clean(ax)
    axes[0].set_ylim(0, 1.05)
    axes[1].set_ylim(0, 3)
    axes[0].legend(fontsize=7, frameon=False, loc="upper center", bbox_to_anchor=(1.1, -0.1), ncol=6)
    fig.suptitle("Prediksi konformal Mondrian: cakupan per kelas dan ukuran set (CV bersarang, blok 10 m, RJDH012)",
                 fontsize=10)
    fig.tight_layout()
    _save(fig, path)


def fig_confusion(y, Ps: dict, best: dict, path) -> None:
    fig, axes = plt.subplots(1, len(Ps), figsize=(11, 3.8))
    for ax, (fs, P) in zip(axes, Ps.items()):
        cm = confusion_matrix(y, cl.predict(P, CLS), labels=CLS)
        cmn = cm / cm.sum(1, keepdims=True).clip(min=1)
        ax.imshow(cmn, cmap="Blues", vmin=0, vmax=1)
        for i in range(3):
            for j in range(3):
                ax.text(j, i, f"{cmn[i, j]:.2f}\n({cm[i, j]})", ha="center", va="center", fontsize=7.5,
                        color="white" if cmn[i, j] > 0.6 else C_INK)
        ax.set_xticks(range(3), CLS, fontsize=7.5)
        ax.set_yticks(range(3), CLS, fontsize=7.5)
        ax.set_xlabel("Prediksi ML (kelas peluang terbesar)", fontsize=8)
        ax.set_ylabel("Kelas uji NAG", fontsize=8)
        s = cl.scores(y, P, CLS)
        ax.set_title(f"Fitur {fs} ({best[fs][0]}): akurasi seimbang {s['bal_acc']:.2f}".replace(".", ","), fontsize=8.5)
    fig.suptitle("Matriks konfusi, validasi tinggalkan-satu-blok 10 m (RJDH012)", fontsize=10)
    fig.tight_layout()
    _save(fig, path)


def fig_shap(X, y, path) -> None:
    m = cl.rf(5).fit(X, y)
    sv = shap.TreeExplainer(m).shap_values(X)
    sv = np.stack(sv, axis=-1) if isinstance(sv, list) else sv          # n × features × classes
    order = [list(m.classes_).index(c) for c in CLS]
    imp = np.abs(sv[:, :, order]).mean(0)
    names = [FEAT_ID.get(f, f) for f in FEATS["lengkap"]]
    o = np.argsort(imp.sum(1))
    fig, ax = plt.subplots(figsize=(6.8, 5.6))
    left = np.zeros(len(o))
    for j, c in enumerate(CLS):
        ax.barh(np.arange(len(o)), imp[o, j], left=left, color=C_CLS[c], label=c)
        left += imp[o, j]
    ax.set_yticks(range(len(o)), [names[i] for i in o], fontsize=7.5)
    ax.set_xlabel("Rata-rata |SHAP| (peluang kelas), dijumlah per kelas", fontsize=8.5)
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    _clean(ax)
    ax.set_title("Kepentingan fitur, model lengkap RJDH012 (Random Forest, leaf 5)", fontsize=9.5)
    _save(fig, path)


def fig_gmm(U1, t1, U2, t2, path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.5))
    for row, (U, t, name) in enumerate(((U1, t1, "U1: RJDH012, rangkaian lengkap"), (U2, t2, "U2: lubang SCIS"))):
        ax = axes[row, 0]
        b = U["bic"].replace(np.inf, np.nan)
        ax.plot(b.index, b - b.min(), "-o", color=C_INK, ms=4)
        ax.axvline(U["k"], color=C_INK2, ls=":")
        ax.set_xticks(list(b.index))
        ax.set_xlabel("Jumlah klaster K", fontsize=8.5)
        ax.set_ylabel("ΔBIC (rata-rata 5 draw)", fontsize=8.5)
        ax.set_title(f"{name} (n {len(U['lab'])}, {U['n_pc']} PC)", fontsize=9)
        _clean(ax)
        ax = axes[row, 1]
        tn = t.div(t.sum(1).clip(lower=1), axis=0)
        ax.imshow(tn.to_numpy(float), cmap="Blues", vmin=0, vmax=1, aspect="auto")
        for i in range(tn.shape[0]):
            for j in range(tn.shape[1]):
                ax.text(j, i, f"{t.iloc[i, j]}", ha="center", va="center", fontsize=8,
                        color="white" if tn.iloc[i, j] > 0.6 else C_INK)
        ax.set_xticks(range(3), CLS, fontsize=8)
        ax.set_yticks(range(len(t)), [f"K{k}" for k in t.index], fontsize=8)
        ax.set_xlabel("Kelas uji NAG (anggota RJDH012)", fontsize=8.5)
        ax.set_ylabel("Klaster GMM (urut S naik)", fontsize=8.5)
        ax.set_title("Klaster vs kelas NAG", fontsize=9)
    fig.suptitle("Klasterisasi tanpa supervisi (GMM pada PCA) dibanding kelas NAG", fontsize=10.5)
    fig.tight_layout()
    _save(fig, path)


def fig_holes(ph, path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), sharey=True)
    y = np.arange(len(ph))
    left = np.zeros(len(ph))
    parts = [(ph["m_NAF"], C_CLS["NAF"], "", CLS_ID["NAF"]), (ph["m_PAF-LC"], C_CLS["PAF-LC"], "", CLS_ID["PAF-LC"]),
             (ph["m_PAF-HC_pasti"], C_CLS["PAF-HC"], "", "PAF-HC pasti (uji NAG atau set tunggal)"),
             (ph["m_PAF-HC"] - ph["m_PAF-HC_pasti"], "#e7a0a8", "///", "PAF-HC mungkin (set memuat PAF-HC)")]
    for v, col, hatch, label in parts:
        axes[0].barh(y, v, left=left, color=col, hatch=hatch, edgecolor="white", lw=0, label=label)
        left += v.to_numpy()
    axes[0].set_xlabel("Panjang (m)", fontsize=8.5)
    axes[0].set_title("Kelas pengelolaan (uji NAG atau ML, konservatif)", fontsize=9)
    axes[0].legend(fontsize=7, frameon=False, loc="lower right")
    tcol = {1: "#1b7837", 2: "#a6dba0", 3: "#c2a5cf", 4: "#762a83"}
    tlab = {1: "1 SCIS dalam domain", 2: "2 SCIS luar domain", 3: "3 S2 pengganti SCIS", 4: "4 tanpa S"}
    left = np.zeros(len(ph))
    for t in (1, 2, 3, 4):
        v = ph.get(f"m_tier{t}", pd.Series(0, index=ph.index)).to_numpy()
        axes[1].barh(y, v, left=left, color=tcol[t], label=tlab[t])
        left += v
    axes[1].plot(ph.m_uji_NAG, y, "k|", ms=10, mew=2, label="usulan uji NAG (m)")
    axes[1].set_xlabel("Panjang (m)", fontsize=8.5)
    axes[1].set_title("Tingkat data (tier) dan usulan uji NAG", fontsize=9)
    axes[1].legend(fontsize=7, frameon=False, loc="lower right")
    axes[0].set_yticks(y, ph.index, fontsize=7.5)
    axes[0].invert_yaxis()
    for ax in axes:
        _clean(ax)
    fig.suptitle("Ringkasan PAF/NAF per lubang bor", fontsize=10.5)
    fig.tight_layout()
    _save(fig, path)


def fig_napp(napp, path) -> None:
    fig, ax = plt.subplots(figsize=(6, 5))
    for c in CLS:
        m = napp.kelas.eq(c)
        ax.scatter(napp.ANC_maks[m].clip(lower=0.05), napp.MPA_SCIS[m].clip(lower=0.05), s=22, c=C_CLS[c],
                   edgecolor="white", lw=0.5, label=f"{c} (n {m.sum()})")
    lim = [0.05, 300]
    ax.plot(lim, lim, color=C_INK, lw=0.8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.text(0.07, 0.11, "MPA = ANC maks", rotation=40, fontsize=7, color=C_INK2)
    ax.set_xlabel("ANC maksimum dari Ca + Mg (kg H₂SO₄/t, batas atas)", fontsize=8.5)
    ax.set_ylabel("MPA dari SCIS, 30,6 × SCIS (kg H₂SO₄/t)", fontsize=8.5)
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    _clean(ax)
    ax.set_title("Proksi NAPP RJDH012: di atas garis, NAPP minimum > 0", fontsize=9.5)
    _save(fig, path)


if __name__ == "__main__":
    main()
