"""AGENTS.md §9.1 comparator: Jansson-style baseline vs our GMMs. Plan: LOG.md, 2026-11-04 entry.

Same cleaned inputs as ML-3 (soil, rock: RJ samples, same elements) and ML-5 (U1: RJDH012; U2: SCIS
rows), dequantisation draw 0 as in each GMM's own fit. Baseline: clr (via ilr, an isometry, so the
MCD covariance is not singular) → robust PCA (MCD; PCs to 80% of robust variance, at most 3) →
k-means k = 2–10 (seed 0, n_init 20), k by a fixed elbow rule (farthest point from the chord), and
k-means at the GMM's K. Compared on: ARI / Cramér's V vs the GMM partition, vs logged alteration
(rock IntrpAltFa; downhole AltFacies), vs oxidation and the RJDH012 NAG classes; WCSS and BIC curves;
bootstrap stability (B = 200; k-means refit end to end, GMMs as in their own scripts). Also writes the
element-selection proposal (≥ 70% > DL and median > 10 × DL vs Stage 1 `ml_usable`); not applied.
Reads data/interim/{03_soil,04_rock,05_assay_joined,01_element_summary}.csv; writes
data/processed/s9_jansson_{scores,curves}.csv, s9_seleksi_unsur.csv,
data/processed/ml/{tanah,batuan}__s9_jansson.csv, outputs/figures/14_jansson_vs_gmm_v1.png.
Run: PYTHONIOENCODING=utf-8 uv run python -W ignore scripts/19_s9_jansson.py  (then scripts/07_export.py)
"""
import importlib.util

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.metrics import adjusted_rand_score

from src import comparators as cp, geostrat as gs, paths, zonation as zn

SEED = 0
N_BOOT = 200
KS = range(2, 11)
C_INK, C_INK2, C_NULL, C_ACC = "#0b0b0b", "#52514e", "#b9b8b2", "#c8321e"
TITLES = {"tanah": "Tanah (RJ)", "batuan": "Batuan (RJ, Au-Cu-As)", "U1": "U1: RJDH012 (S, Fe, K, Ba, Sr, Zn, Mn)",
          "U2": "U2: baris SCIS (S, Au, Ag, Cu, As)"}


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), paths.ROOT / "scripts" / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def baseline(L: np.ndarray, k_ref: list[int]) -> dict:
    Z = cp.ilr_from_log(L)
    rp = cp.RobustPCA(Z)
    T = rp.transform(Z)
    curve = cp.wcss_curve(T, KS)
    k_e = cp.elbow(curve)
    labs = {k: cp.order_by(cp.kmeans(T, k).labels_, L[:, 0]) for k in sorted({k_e, *k_ref})}
    return dict(rp=rp, T=T, curve=curve, k_elbow=k_e, labs=labs)


def boot_kmeans(L: np.ndarray, k: int, b: int) -> np.ndarray:
    rng = np.random.default_rng(SEED + 2000 + b)
    i = rng.integers(0, len(L), len(L))
    rp = cp.RobustPCA(cp.ilr_from_log(L[i]))
    km = cp.kmeans(rp.transform(cp.ilr_from_log(L[i])), k, n_init=5)
    return km.predict(rp.transform(cp.ilr_from_log(L)))


def stats(name: str, method: str, k: int, lab: np.ndarray, ref: dict, boot_ari: np.ndarray | None, extra=None) -> dict:
    row = {"kasus": name, "metode": method, "k": int(k), "n": len(lab)}
    for rname, rv in ref.items():
        m = pd.notna(rv)
        if m.sum() < 5:
            continue
        rv = np.asarray(rv, object)[m]
        row[f"ARI_{rname}"] = adjusted_rand_score(rv.astype(str), lab[m])
        row[f"V_{rname}"] = zn.cramers_v(rv.astype(str), lab[m])
        row[f"n_{rname}"] = int(m.sum())
    if boot_ari is not None:
        row |= {"boot_ARI_med": float(np.median(boot_ari)), "boot_ARI_05": float(np.percentile(boot_ari, 5)),
                "boot_ARI_95": float(np.percentile(boot_ari, 95))}
    return row | (extra or {})


def run_case(name, L, gmm_lab, gmm_k, gmm_bic, gmm_boot, refs, rows_out, curves_out):
    base = baseline(L, [gmm_k])
    ref = {"GMM": gmm_lab, **refs}
    rows_out.append(stats(name, "GMM (pipeline kami)", gmm_k, gmm_lab, {k: v for k, v in refs.items()}, gmm_boot))
    for k, lab in base["labs"].items():
        tag = "elbow" if k == base["k_elbow"] else "K_GMM"
        if k == base["k_elbow"] and k == gmm_k:
            tag = "elbow = K_GMM"
        boots = np.array(Parallel(n_jobs=-1)(delayed(boot_kmeans)(L, k, b) for b in range(N_BOOT)))
        ari = zn.boot_ari(lab, boots)
        rows_out.append(stats(name, f"k-means ({tag})", k, lab, ref, ari,
                              {"n_PC": base["rp"].n_pc, "var_PC": float(base["rp"].evr[:base["rp"].n_pc].sum())}))
    for k, w in base["curve"].items():
        curves_out.append({"kasus": name, "k": k, "wcss": w, "dBIC_gmm": np.nan})
    b = gmm_bic - np.nanmin(gmm_bic[np.isfinite(gmm_bic)])
    for k, v in b.items():
        curves_out.append({"kasus": name, "k": int(k), "wcss": np.nan, "dBIC_gmm": v})
    print(f"{name}: n {len(L)}, robust PCs {base['rp'].n_pc} ({base['rp'].evr[:base['rp'].n_pc].sum():.0%}), "
          f"elbow k {base['k_elbow']}, GMM K {gmm_k}")
    return base


def surface(m10, rows_out, curves_out, ml_out):
    tables = {n: pd.read_csv(paths.INTERIM / f, low_memory=False) for n, (f, *_) in m10.DATASETS.items()}
    for name, (_f, _l, feats, extra) in m10.DATASETS.items():
        d = tables[name]
        r = m10.run_dataset(name, d, feats)
        L = zn.log_matrix(r["V"], np.random.default_rng(SEED))   # draw 0 of the ML-3 pipeline
        refs = {}
        if "IntrpAltFa" in d:
            refs["alterasi"] = d.loc[r["rows"], "IntrpAltFa"].to_numpy(object)
        base = run_case(name, L, r["zone"], 3, r["bic"], r["ari"], refs, rows_out, curves_out)
        ml = pd.DataFrame({"SampleID": d.loc[r["rows"], "SampleID"].to_numpy()})
        ml["ML_s9_kmeans"] = base["labs"][base["k_elbow"]]
        ml["ML_s9_kmeans_k"] = base["k_elbow"]
        ml["ML_s9_kmeans_k3"] = base["labs"][3]
        ml_out[name] = ml
        if extra:   # rock: all 7 elements where complete (closer to a multi-element Jansson input)
            cols = [f"{x}_ml" for x in feats + extra]
            ok = d.loc[r["rows"], cols].notna().all(axis=1).to_numpy()
            L7 = zn.log_matrix(d.loc[r["rows"][ok], cols].to_numpy(float), np.random.default_rng(SEED))
            b7 = baseline(L7, [3])
            ref7 = {"GMM": r["zone"][ok], "alterasi": refs["alterasi"][ok]}
            for k, lab in b7["labs"].items():
                rows_out.append(stats(f"{name}_7unsur", f"k-means ({'elbow' if k == b7['k_elbow'] else 'K_GMM'})", k,
                                      lab, ref7, None, {"n_PC": b7["rp"].n_pc,
                                                         "var_PC": float(b7["rp"].evr[:b7["rp"].n_pc].sum())}))
            rows_out.append(stats(f"{name}_7unsur", "GMM (pipeline kami)", 3, r["zone"][ok], {"alterasi": ref7["alterasi"]},
                                  None))


def downhole(m14, rows_out, curves_out):
    a = m14.load()
    summ = pd.read_csv(paths.INTERIM / "01_element_summary.csv")
    ok = ~a.no_sample.to_numpy()
    has_scis = a.S_src.eq("SCIS").to_numpy()
    cases = {"U1": (a.SiteID.eq("RJDH012").to_numpy() & ok
                    & a[[f"{c}_ml" for c in m14.U1_COLS]].notna().all(1).to_numpy(), m14.U1_COLS),
             "U2": (ok & has_scis & a[[f"{c}_ml" for c in m14.U2_COLS]].notna().all(1).to_numpy(), m14.U2_COLS)}
    for name, (rows, cols) in cases.items():
        V, cens, dl = m14.censored_matrix(a, rows, cols, summ)
        U = m14.gmm_pipeline(V, cens, dl)
        main = U["gmm"].predict_proba(U["T0"])[:, U["order"]].argmax(1) + 1
        ref_means = U["gmm"].means_[U["order"]]
        boots = np.array(Parallel(n_jobs=-1)(delayed(m14.boot_job)(b, U["T0"], U["k"], U["reg"], ref_means)
                                             for b in range(N_BOOT)))
        L = gs.log_features(V, cens, dl, np.random.default_rng(SEED))   # draw 0 of the ML-5 pipeline
        refs = {"NAG3": a.nag_cls[rows].to_numpy(object), "oksidasi": a.ox_used[rows].to_numpy(object),
                "alterasi": a.AltFacies[rows].to_numpy(object)}
        run_case(name, L, U["lab"], U["k"], U["bic"], zn.boot_ari(main, boots), refs, rows_out, curves_out)


def selection_proposal(summ: pd.DataFrame) -> pd.DataFrame:
    files = {"assay": "05_assay_joined.csv", "rock": "04_rock.csv", "soil": "03_soil.csv"}
    rows = []
    for ds, f in files.items():
        d = pd.read_csv(paths.INTERIM / f, low_memory=False)
        for r in summ[summ.dataset.eq(ds) & summ.pct_analysed.gt(0)].itertuples():
            c = f"{r.column}_ml"
            if c not in d:
                continue
            v = pd.to_numeric(d[c], errors="coerce").dropna()
            if not len(v):
                continue
            dl = r.harmonised_dl if pd.notna(r.harmonised_dl) else 2 * v[v > 0].min()   # job DLs: floor is DL/2
            above = r.pct_analysed / 100 * (1 - (r.pct_cens_harmonised if pd.notna(r.pct_cens_harmonised) else 0) / 100)
            med_dl = float(v.median() / dl) if dl > 0 else np.nan
            rows.append({"dataset": ds, "kolom": r.column, "pct_di_atas_DL": round(100 * above, 1),
                         "median_per_DL": round(med_dl, 2), "aturan_jansson": bool(above >= 0.70 and med_dl > 10),
                         "ml_usable": bool(r.ml_usable),
                         "DL_sumber": "harmonised" if pd.notna(r.harmonised_dl) else "2 × lantai (DL job)"})
    return pd.DataFrame(rows)


def fig_curves(curves: pd.DataFrame, scores: pd.DataFrame, path):
    names = list(TITLES)
    fig, axes = plt.subplots(2, 4, figsize=(14, 6.2))
    for j, name in enumerate(names):
        c = curves[curves.kasus.eq(name)]
        w = c.dropna(subset=["wcss"])
        ax = axes[0, j]
        y = w.wcss / w.wcss.max()
        ax.plot(w.k, y, "-o", color=C_INK, ms=4, lw=1.5)
        ke = scores.loc[scores.kasus.eq(name) & scores.metode.str.contains("elbow"), "k"]
        if len(ke):
            ke = int(ke.iloc[0])
            ax.plot([ke], [y[w.k.eq(ke)].iloc[0]], "o", ms=11, mfc="none", mec=C_ACC, mew=2)
            ax.annotate(f"siku k={ke}", (ke, y[w.k.eq(ke)].iloc[0]), xytext=(8, 8), textcoords="offset points",
                        fontsize=8, color=C_ACC)
        ax.set_title(TITLES[name], fontsize=9)
        ax.set_xlabel("k (k-means)", fontsize=8.5)
        if j == 0:
            ax.set_ylabel("WCSS relatif (k-means, baseline)", fontsize=8.5)
        b = c.dropna(subset=["dBIC_gmm"])
        ax = axes[1, j]
        fin = np.isfinite(b.dBIC_gmm)
        ax.bar(b.k[fin], b.dBIC_gmm[fin], color=C_NULL, width=0.6)
        kbest = int(b.k[b.dBIC_gmm.eq(0)].iloc[0])
        top = float(b.dBIC_gmm[fin].max())
        ax.plot([kbest], [0], "v", color=C_INK, ms=8, clip_on=False)
        ax.annotate("terbaik", (kbest, 0), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=7.5)
        for k in b.k[~fin]:
            ax.text(k, 0.02 * top, "tidak\nsah", ha="center", va="bottom", fontsize=7, color=C_INK2)
        ax.set_xticks(b.k.astype(int))
        kg = int(scores.loc[scores.kasus.eq(name) & scores.metode.str.startswith("GMM"), "k"].iloc[0])
        ax.set_title(f"GMM kami: K dipakai = {kg}, BIC terbaik = {kbest}", fontsize=9)
        ax.set_xlabel("K (GMM)", fontsize=8.5)
        if j == 0:
            ax.set_ylabel("ΔBIC terhadap K terbaik", fontsize=8.5)
        for a_ in axes[:, j]:
            a_.spines[["top", "right"]].set_visible(False)
            a_.tick_params(labelsize=8)
    fig.suptitle("Pembanding §9.1: kurva siku k-means (clr → PCA robust) vs BIC GMM pada data yang sama", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main():
    m10, m14 = load_script("10_ml3_zonation.py"), load_script("14_ml5_paf.py")
    rows, curves, ml_out = [], [], {}
    surface(m10, rows, curves, ml_out)
    downhole(m14, rows, curves)
    scores = pd.DataFrame(rows)
    curves = pd.DataFrame(curves)
    summ = pd.read_csv(paths.INTERIM / "01_element_summary.csv")
    sel = selection_proposal(summ)
    P = paths.PROCESSED
    scores.round(4).to_csv(P / "s9_jansson_scores.csv", index=False)
    curves.round(4).to_csv(P / "s9_jansson_curves.csv", index=False)
    sel.to_csv(P / "s9_seleksi_unsur.csv", index=False)
    for name, ml in ml_out.items():
        assert not ml.SampleID.duplicated().any()
        ml.to_csv(P / "ml" / f"{name}__s9_jansson.csv", index=False)
    fig_curves(curves, scores, paths.FIGURES / "14_jansson_vs_gmm_v1.png")
    show = [c for c in ["kasus", "metode", "k", "n", "n_PC", "ARI_GMM", "V_GMM", "ARI_alterasi", "V_alterasi",
                        "ARI_oksidasi", "V_oksidasi", "ARI_NAG3", "V_NAG3", "boot_ARI_med"] if c in scores]
    print(scores[show].round(3).to_string(index=False))
    for ds, g in sel.groupby("dataset"):
        print(f"{ds}: Jansson rule {sorted(g.kolom[g.aturan_jansson])}; ml_usable {sorted(g.kolom[g.ml_usable])}")


if __name__ == "__main__":
    main()
